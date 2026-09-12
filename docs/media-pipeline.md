# Media pipeline

How a photo or video goes from an upload to what the feed serves. Everything
runs on the existing stack: Django stores the original, a Celery worker encodes
it with FFmpeg/Pillow, and both the original and the output live in the Ethio
Telecom OBS bucket (S3-compatible, credentials from Vault as before). There is
no CDN; processed objects are public-read URLs on OBS.

## Flow

```
client ──multipart──▶ /posts/create/ ─┐   (also POST /reels/, /campaigns/posts/create/,
                                      │    and PATCH /reels/<id>/ with a new file)
                                      ▼
            validate (real type, size, pixels) ─▶ store original, private:
                                                  source/<videos|images>/<user>/<uuid>.<ext>
                                      │
                                      ▼
            Reel row, processing_status=PROCESSING ─▶ 201 to the client
                                      │ (after commit)
                                      ▼
            Celery process_reel_media ─▶ processed/<videos|images|thumbnails>/<reel>/v<N>/…
                                      │
                                      ▼
            processing_status=READY ─▶ appears in feeds
```

No FFmpeg runs inside the HTTP request. The request only checks the file and
stores it; the answer comes as soon as the bytes are in OBS.

## Status

| `processing_status` | Meaning | Who sees the post |
|---|---|---|
| `PROCESSING` | stored, being encoded | its author (own profile, post page) |
| `READY` | encoded; `media`/`image` are the served files | everyone |
| `FAILED` | could not be processed; `processing_error` has a code | its author |

`UPLOADING` exists for clients; the API never stores it. Posts from before the
pipeline are `READY` and are served exactly as they were.

Failure codes: `invalid_media`, `video_too_long`, `source_missing`,
`long_video_unpaid`, `storage_write_failed` (the encode worked but OBS refused
the output -- a configuration problem; the reason is in the worker's
`[TASKS] S3/OBS upload failed` warning), `processing_failed` (other transient
errors outlasted the retries). The web app shows the author a plain sentence
for each, never the code.

## What is produced

**Video** -- H.264 High / AAC, yuv420p, faststart, metadata (GPS included)
stripped, at most 30 fps. Rungs by the *short* side, never upscaled, aspect
kept: 720 (`media`), 480 and 360 (`media_variants`). A source smaller than 360
gets one encode at its own size. A 320x720 JPEG thumbnail from the encode.

A rung at the upload's own size that comes out *no smaller* than the upload
(an efficient 720p H.264 file does this) is replaced by the upload's own
streams, re-wrapped: faststart, metadata stripped, no re-encode. Only when the
upload is already what browsers play -- H.264 8-bit 4:2:0, AAC or silent,
upright, at most 30 fps, MP4/MOV; anything else (browser WebM, HEVC, 10-bit,
rotated) keeps its encode, because playing everywhere matters more than bytes.

**Photo** -- orientation applied, EXIF dropped, at most 1080 px: progressive
JPEG (`image`), 360/720 px wide variants (`image_variants`), and WebP twins of
all three (`image_webp_variants`). A WebP is kept only when it is at least 10%
smaller than its JPEG (`WEBP_MIN_SAVING`); otherwise that size is JPEG only. A
thumbnail. The full-size WebP keeps transparency; the JPEGs and width variants
are flattened.

A blurhash follows either.

### Measured

The pipeline's own functions on sample files (local dev media plus two
synthetic camera-like clips at a phone's bitrate). Real uploads vary; the
per-post numbers are logged as `media.processed ... source_bytes output_bytes`.

| Source | Original | 360p | 480p | 720p |
|---|---|---|---|---|
| phone-style 9:16 1080x1920, 12 Mb/s H.264, 10 s | 14.5 MB | 322 KB (2%) | 550 KB (4%) | 3.08 MB (21%) |
| phone-style 16:9 1920x1080, 12 Mb/s H.264, 10 s | 14.6 MB | 308 KB (2%) | 530 KB (4%) | 3.21 MB (22%) |
| browser recording, 640x480 VP8/Opus, 24 s | 7.48 MB | 460 KB (6%) | 693 KB (9%) | -- (source is 480p) |
| browser recording, 640x480 VP8/Opus, 14 s | 4.50 MB | 279 KB (6%) | 500 KB (11%) | -- |
| 1280x720 H.264 at 1.5 Mb/s, 17 s | 3.09 MB | 589 KB (19%) | 950 KB (30%) | 3.09 MB (100%, re-wrapped: already efficient) |
| 576x1024 H.264 at 0.55 Mb/s, 24 s | 1.57 MB | 736 KB (46%) | 1.15 MB (73%) | -- |

| Photo | Original | full JPEG | full WebP | 720w JPEG / WebP | 360w JPEG / WebP |
|---|---|---|---|---|---|
| 1080x1591 JPEG | 866 KB | 111 KB | 68 KB | 97 / 61 KB | 29 / 19 KB |
| 1080x1638 JPEG | 723 KB | 92 KB | 53 KB | 85 / 49 KB | 25 / 15 KB |
| 1920x1080 PNG screenshot | 1.58 MB | 69 KB | 36 KB | 35 / 20 KB | 12 / 8 KB |

Thumbnails: 7-46 KB.

## API fields

`ReelSerializer` adds, without removing anything:

- `processing_status`, `processing_error`, `media_type` (`video`/`image`, known
  while processing)
- `media_variants` `{"360", "480"}`, `image_variants` `{"360", "720"}`,
  `image_webp_variants` `{"360", "720", "full"}` -- a key is absent when that
  file does not exist

While a post is not READY its `media`/`image`/`thumbnail` are `null`: the
original is private and never served.

The campaign feed (`/campaigns/<id>/feed/`) and campaign entries
(`/campaigns/<id>/`) carry the same media fields (`reel_media_payload`), and
list an entry that is not READY only to its author. Views that build a URL by
hand use `served_url`, which never returns a `source/` key.

## Web client

- **Upload** (`pages/general/EnhancedPostPage.jsx`): sends `client_upload_id`,
  the same on every retry of a post and, for a gallery file, across a reload of
  the page (`utils/uploadId.js`, sessionStorage, 30 minutes, cleared on
  success). The success screen says the post is being prepared.
- **Processing state** (`components/common/MediaProcessingState.jsx`): the
  author's PROCESSING / FAILED posts show a placeholder on the post page, the
  profile grid, the post viewer and campaign entries, and swap in the media
  when READY (`hooks/usePostProcessing.js`: one request per post after 3, 5, 8
  and 13 s, then every 15 s, stopping at READY/FAILED or after 15 minutes).
- **Renditions** (`utils/connection.js`): slow connection 360p, normal 480p,
  fast 720p. The home feed, Reels, the post page, both viewers and the
  campaign pages (`components/feed/ProcessedMedia.jsx`) all choose this way.
  Photos in the home feed, post page, profile grid and campaign pages are a
  `<picture>` with the WebP rung and the JPEG fallback.
- **Playback**: one video at a time everywhere -- the most visible card in the
  home feed and Reels, the one last started on campaign pages -- and nothing
  downloads a video before it is needed (thumbnail as poster, `preload`
  `none`/`metadata`, no `autoPlay` attribute in Reels).
- **Edit Post** (profile): replacement media is sent with a `client_upload_id`
  too, so a retried edit is recognised rather than refused with 409.

## Retries and duplicates

- **Client retries.** Send `client_upload_id` (form field) or an
  `Idempotency-Key` header, 8-64 of `[A-Za-z0-9_.:-]`, the same for every retry
  of one post. A repeat returns the existing post with `200`, charged once.
  Campaign entries (`/campaigns/posts/create/`) and media replacement
  (`PATCH /reels/<id>/`) honour it the same way.
- **Replacing media.** `PATCH /reels/<id>/` with a file runs the same intake
  (type, size, video subscription) and makes the post PROCESSING with every
  derived field cleared, so nothing of the old media is served. The replaced
  original is deleted after the change commits; the old processed files stay
  until the new media is READY, then the worker removes them. Replacing media
  while the post is still PROCESSING is refused with 409 `post_processing`.
- **Worker retries.** 3 retries, 60 s apart, same task id. A post is claimed by
  one task at a time (`processing_task_id`); a claim older than 30 minutes is
  considered abandoned. A run that loses its claim writes nothing. Output keys
  are versioned (`v<N>`), so a retry or re-process never overwrites a file a
  client may have cached; the superseded version is deleted after the new one
  is in place.
- **Stuck posts.** `redrive_stuck_media` (every 10 minutes) re-queues posts
  whose task never arrived or whose worker died.

## Configuration

| Setting | Default | |
|---|---|---|
| `MEDIA_MAX_UPLOAD_BYTES` | 52428800 (50 MB) | larger uploads get 413 |
| `MEDIA_MAX_VIDEO_SECONDS` | 92 | longer videos FAIL with `video_too_long` |
| `MEDIA_MAX_IMAGE_PIXELS` | 40000000 | larger photos get 400 `image_too_large` |
| `MEDIA_SOURCE_RETENTION_DAYS` | 0 | 0 keeps originals forever |

With retention above 0, `purge_processed_sources` (daily) deletes originals of
posts that have been READY for that many days -- only after confirming the
processed file exists in storage, and never for a post that is not READY.
Deleting a post removes its original and all its processed versions.

Processed objects are written with `Cache-Control: public, max-age=31536000,
immutable` (their keys never change content); originals with
`private, no-store`.

### Public or private bucket

The worker writes with exactly the ACL the web process uses:

| `S3_DEFAULT_ACL` | Objects written | Media URLs the API returns |
|---|---|---|
| `public-read` (default) | public-read; originals explicitly private | plain, stable URLs |
| empty | no ACL header at all (the bucket's default, private) | signed (`S3_QUERYSTRING_AUTH` follows) |

On a private bucket the worker still records processed media as
`{S3_ENDPOINT_URL}/{bucket}/{key}`; the API signs those on the way out
(`servable_url`), as it signs every other media URL. Signed URLs change on
every response, so browsers cannot cache them across visits -- the price of a
private bucket.

The S3 client libraries (`botocore`, `boto3`, `s3transfer`, `urllib3`) log at
WARNING whatever `LOG_LEVEL` is: at DEBUG they write about ten lines per
signed URL, signature included.

## Operations

```
# re-process specific posts (always queues)
python manage.py reprocess_media --reel 123 --reel 456

# every FAILED post: dry run, then queue. After fixing a storage problem,
# this brings back the posts that failed on it -- their originals are intact.
python manage.py reprocess_media --failed
python manage.py reprocess_media --failed --commit

# older posts that went out as their raw upload: dry run, then queue.
# Only READY posts the current pipeline has never finished; they stay
# visible on their current media while they are re-encoded.
python manage.py generate_missing_media
python manage.py generate_missing_media --commit
# older photos that have JPEG variants but no WebP (not in the default run)
python manage.py generate_missing_media --only webp --commit
```

Run the backfill once after deploying: until then, posts made through
`/posts/create/` before this change are still served as their original upload.

A post whose original was removed under the retention setting cannot be
re-processed; the command reports it.

Logs: `media.processed reel=… kind=… seconds=… source_bytes=… output_bytes=…`,
`media.failed reel=… code=…`, `media.superseded`, `media.retention …`.

## Tests

`tests/integration/test_media_pipeline.py` -- intake, category, idempotency,
visibility, editing and deleting, retries, retention, campaign feed and
entries, the backfill filter, and real FFmpeg encodes (9:16, 16:9, 1:1,
360p-1080p, with and without audio, rotated, WebM, tiny, an efficient upload
that must not grow). The FFmpeg tests skip when `ffmpeg` is not installed;
CI's integration job installs it.

Web: `tests/mediaPipeline.test.js` (`npm test`) for the pickers, status, upload
ids and polling; `tests/browser/media.harness.jsx` (`npm run test:browser --
media`) plays real recorded clips through the post page, Reels and the
campaign feed and checks, from the server's request log, which files the
browser fetched -- the right rung, WebP instead of JPEG, and never a
`source/` original.
