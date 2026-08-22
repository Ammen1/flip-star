from django.http import StreamingHttpResponse, FileResponse, Http404
from django.views.decorators.http import require_http_methods
from django.conf import settings
import os
import re

@require_http_methods(["GET", "HEAD"])
def serve_video(request, path):
    """
    Serve video files with proper range request support for streaming
    """
    file_path = os.path.join(settings.MEDIA_ROOT, 'reels', path)
    
    if not os.path.exists(file_path):
        raise Http404(f"Video not found: {file_path}")
    
    file_size = os.path.getsize(file_path)
    content_type = 'video/webm' if path.endswith('.webm') else 'video/mp4'
    
    # Handle range requests for video streaming
    range_header = request.META.get('HTTP_RANGE', '').strip()
    range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
    
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
        
        if start >= file_size or end >= file_size:
            response = StreamingHttpResponse(status=416)
            response['Content-Range'] = f'bytes */{file_size}'
            return response
        
        length = end - start + 1
        
        with open(file_path, 'rb') as f:
            f.seek(start)
            data = f.read(length)
        
        response = StreamingHttpResponse(
            data,
            status=206,
            content_type=content_type
        )
        response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        response['Content-Length'] = str(length)
        response['Accept-Ranges'] = 'bytes'
        
    else:
        # Full file response
        response = FileResponse(
            open(file_path, 'rb'),
            content_type=content_type
        )
        response['Content-Length'] = str(file_size)
        response['Accept-Ranges'] = 'bytes'
    
    return response
