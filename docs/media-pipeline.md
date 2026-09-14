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
`[TASKS] S3/OBS upload failed` warning), `record_failed` (the result could not
be written to the post's row -- deterministic, so not retried; this is what a
100-character `thumbnail` column did with OBS URLs before migration 0119
widened `media`, `image` and `thumbnail` to 500), `processing_failed` (other
transient errors outlasted the retries). The web app shows the author a plain sentence
for each, never the code.

### Progress

`processing_progress` (0-100) is how far the worker actually is, written by
the task that holds the claim -- never estimated from elapsed time:

| Stage | Video | Photo | Measured from |
|---|---|---|---|
| fetch the original | 0-5 | 0-10 | bytes copied / object size |
| probe | 6 | -- | |
| encode / render | 6-92 | 10-50 | FFmpeg `-progress pipe:1` `out_time` / duration; photo outputs rendered |
| store outputs | 92-99 | 50-99 | share of the output bytes stored in OBS |

Video rungs are weighted by their pixel count (a 720p encode is most of the
work). A row is written once a second at most, sooner only when the value has
moved 5 points, and only by the run holding `processing_task_id`, so a run
that lost its claim cannot move a bar. The worker stops at 99; 100 is written with READY in the same update. A
retry starts again from 0, as does replacing the media; re-encoding a post
that is already READY (the backfill) leaves it at 100.

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
  while processing), `processing_progress` (100 once READY)
- `media_variants` `{"360", "480"}`, `image_variants` `{"360", "720"}`,
  `image_webp_variants` `{"360", "720", "full"}` -- a key is absent when that
  file does not exist

While a post is not READY its `media`/`image`/`thumbnail` are `null`: the
original is private and never served.

The campaign feed (`/campaigns/<id>/feed/`) and campaign entries
(`/campaigns/<id>/`) carry the same media fields (`reel_media_payload`), and
list an entry that is not READY only to its author. Views that build a URL by
hand use `served_url`, which never returns a `source/` key.

`GET /posts/processing/` is the batched status for the upload indicator: the
caller's own posts only, one small query, no media URLs.

```
GET /api/v1/posts/processing/?ids=12,13     # those posts, any status (at most 20)
GET /api/v1/posts/processing/               # own posts PROCESSING from the last day

{"posts": [{"id": 12, "processing_status": "PROCESSING", "processing_progress": 60,
            "processing_error": null, "media_type": "video", "queued": false,
            "created_at": "…"}]}
```

`queued` is true while no worker has started the post yet. A post that is not
the caller's, or no longer exists, is simply absent from `posts`.

## Web client

- **Upload** (`pages/general/EnhancedPostPage.jsx`): sends `client_upload_id`,
  the same on every retry of a post and, for a gallery file, across a reload of
  the page (`utils/uploadId.js`, sessionStorage, 30 minutes, cleared on
  success). As soon as the API accepts the upload (201 with the PROCESSING
  post) the app goes to Home -- no success screen, no waiting for FFmpeg -- and
  the upload moves to the corner indicator. A campaign entry is tracked the
  same way.
- **Upload indicator** (`components/common/UploadProgressIndicator.jsx`, top
  right of every page): a ring around a small thumbnail of the upload (made
  in the browser from the chosen file, `utils/uploadThumb.js`) with the worker's
  own `processing_progress` -- "Waiting to process…" while `queued`, then 25%,
  60%… The ring eases between readings; the number is always the last one the
  server gave, and nothing counts up on a timer. At READY it shows "Posted"
  for 2.5 s and goes; Home puts the post at the top of the feed without a
  reload (`flipstar:post-ready`). At FAILED it stays, with the same plain
  sentence as the post page and a Dismiss button. Tapping one opens the post
  page. Up to three show, then "+N more uploading".
- **Tracking** (`utils/uploadTracker.js`, one instance in
  `services/uploadTracker.js`): every upload being processed is kept in
  localStorage (`flipstar.processingUploads.v1`), so a refresh or a new tab
  picks the list up and carries on; to catch uploads the list does not have
  (storage cleared, another device) the app asks `GET /posts/processing/` (no
  ids) once when it starts signed in. However many uploads
  there are, each tick is **one** request, `GET /posts/processing/?ids=…`.
  Only one tab polls (a Web Lock, `flipstar-processing-poller`); the others
  follow through `storage` events and take over if it closes. Every 2 s for
  the first 3 minutes of an upload, then 5 s, then 15 s; an entry older than
  2 hours is dropped. At READY the full post is fetched once and the `/reels`
  cache cleared. Signing out clears the list.
- **Processing state** (`components/common/MediaProcessingState.jsx`): the
  author's PROCESSING / FAILED posts show a placeholder on the post page, the
  profile grid, the post viewer and campaign entries, and swap in the media
  when READY. `hooks/usePostProcessing.js` watches through the same tracker,
  so a post open on its page while it is in the indicator is still one
  request per tick, not two.
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
- **Media that stops loading** (an expired signature, a replaced or lost file):
  every player refreshes and retries through `services/mediaRecovery.js`
  before it says unavailable -- see "When a video will not load".

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
| `S3_QUERYSTRING_EXPIRE` | 3600 | seconds a signed media URL works (private bucket); see "When a video will not load" |

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

## When a video will not load

**Why it happened.** On a private bucket (staging) every media URL is signed
and works for `S3_QUERYSTRING_EXPIRE` seconds -- an hour by default. The web
app held those URLs for as long as a page stayed open and replayed them from
its feed caches; OBS then answers 403, which a `<video>` reports as error 4.
The Reels card hid its player on the first error and read "Video
unavailable" for good, even once fresh media arrived, and nothing on the
server heard about it. A post edited or re-processed since the client
fetched it has the same symptom: its old version's files are removed.

**What happens now.**

- *Before a URL runs out* the web app asks for new ones:
  `hooks/useFreshMedia.js` a little before each post's earliest signature
  expires, and Reels once a minute for every loaded card -- one request for
  up to 20 posts. A playing clip keeps its file until it stops or its URL is
  about to die.
- *Feed caches* (Reels, Home, Profile, campaign feed) are never shown when a
  URL in them has run out or will within five minutes (`utils/signedUrl.js`).
- *A load that fails anyway* is reported to `POST /api/v1/posts/media/` with
  the URL, the media error and the screen; the server works out why, logs it,
  and answers with the post's media signed now, less any rendition storage
  has lost. The player swaps it in and carries on where it stopped. A post
  is retried at most twice in ten minutes (`utils/mediaRecovery.js`); only
  then does it say unavailable. Never an original.

```
POST /api/v1/posts/media/
{"ids": [12, 13],
 "failures": [{"id": 12, "url": "<the URL that did not load>", "error": "4", "surface": "reels"}]}

{"posts": [{"id": 12, "media": "...", "media_variants": {...}, "thumbnail": "...", ...,
            "media_check": {"reason": "expired_signature", "repairing": false}},
           {"id": 13, ..., "media_check": null}],
 "expires_in": 3600}
```

Same visibility as the feed (moderation, READY or own), anonymous allowed,
20 ids and 5 failures per request, throttled (`media_refresh`, 120/min).

**The reasons**, in the answer and in the log (`api/services/media_availability.py`):

| `reason` | Meaning | What to do |
|---|---|---|
| `expired_signature` | the URL was signed longer ago than `S3_QUERYSTRING_EXPIRE` | nothing; expected for pages left open |
| `superseded` | the URL is for media the post no longer has (edited, re-processed) | nothing |
| `object_missing` | storage has no such object (404) | the post is re-processed from its original automatically, once per 30 min; `check_media` lists others |
| `access_denied` | OBS refused the API's own credentials (403) | bucket policy / ACL of that object |
| `storage_error` | OBS did not answer (timeout, 5xx) | OBS status, network from the pods |
| `clock_skew` | the object is there, but OBS's clock is more than 2 min from ours | NTP on the API nodes -- signatures from a skewed clock are refused |
| `unsigned` | an unsigned URL into the private bucket | the stored URL's host does not match `S3_ENDPOINT_URL` |
| `original_requested` | a URL into `source/` | a client bug; originals are never served |
| `external` | not this app's storage (old Cloudinary URL) | re-upload or re-process the post |
| `not_ready` | the post is processing or failed | nothing |
| `available` | nothing wrong on the server's side: the object is there and a fresh URL is valid | the browser: network, codec (see `error`) |

Log lines -- one per reported failure; the key, never the signature:

```
media.unavailable reel=50 field=media_480 reason=expired_signature status=- skew=- surface=reels error=4 key=processed/videos/50/v1/480p.mp4 missing=- repairing=False viewer=17
media.unavailable reel=51 field=media reason=object_missing status=404 skew=0 surface=home error=4 key=processed/videos/51/v2/720p.mp4 missing=media,media_480 repairing=True viewer=anon
media.repair_queued reel=51 missing=media,media_480
```

`expired_signature`, `superseded` and `not_ready` are INFO; `clock_skew`,
`unsigned`, `external` and `available` WARNING; the rest ERROR. Storage is
asked (HEAD, the app's credentials) only when the URL itself does not explain
the failure, and one answer is reused for a minute.

**From the server's side**, without waiting for a viewer:

```
python manage.py check_media                  # READY posts of the last 7 days
python manage.py check_media --reel 50 --reel 51
python manage.py check_media --days 30 --repair   # ... and re-process posts with missing files
```

It HEADs every rendition each post advertises, prints missing (404), denied
(403) or unreachable files, how URLs are signed and for how long, and the
clock difference between the pod and OBS.

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

Migrations: `0119` widens `media`, `image` and `thumbnail` to 500 characters,
`0120` adds `processing_progress` (default 0). On PostgreSQL both are
catalogue-only changes -- no table rewrite. Deploy the API and the worker
image together: a worker without `0120` cannot report progress, and the API
reads the column.

A post whose original was removed under the retention setting cannot be
re-processed; the command reports it.

Logs: `media.processed reel=… kind=… seconds=… source_bytes=… output_bytes=…`,
`media.failed reel=… code=…`, `media.superseded`, `media.retention …`.

## Tests

`tests/integration/test_media_pipeline.py` -- intake, category, idempotency,
visibility, editing and deleting, retries, retention, campaign feed and
entries, the backfill filter, progress (the status endpoint, throttling, a
retry resetting it, FFmpeg's progress lines, and a real 12 s encode that must
report values from inside a rung, not only as each one ends), and real FFmpeg encodes
(9:16, 16:9, 1:1, 360p-1080p, with and without audio, rotated, WebM, tiny, an
efficient upload that must not grow). The FFmpeg tests skip when `ffmpeg` is
not installed; CI's integration job installs it.

Web: `tests/mediaPipeline.test.js` (`npm test`) for the pickers, status, upload
ids and the upload tracker (one request per tick for many uploads, refresh,
two tabs, READY/FAILED/expiry); `tests/browser/media.harness.jsx` (`npm run
test:browser -- media`) plays real recorded clips through the post page, Reels
and the campaign feed and checks, from the server's request log, which files
the browser fetched -- the right rung, WebP instead of JPEG, and never a
`source/` original -- and drives the corner indicator through the percentages
the stub server reports, a failure, a reload and several uploads at once.
`camera.harness.jsx` checks that posting lands on Home with the upload in the
indicator.

Media that stops working: `tests/integration/test_media_availability.py`
(refresh signing, every diagnosis reason against a fake OBS -- expired,
superseded, missing, 403, 5xx, unreachable, clock skew, unsigned, originals --
missing renditions left out, repair queued once, visibility, the feed signing
afresh on each request, `check_media`); `tests/mediaRecovery.test.js` (URL
expiry parsing, batching, shared requests, the retry limit, offline); and in
the browser the stub signs URLs as a private bucket does and answers 403/404
the way OBS does: an expired URL in Reels is reported and replaced and the
clip plays, a lost rung falls back to one that exists, a post with no files
left says "Video unavailable" once without looping, a cached feed with dead
URLs is not replayed, and the campaign feed and post page recover too.
