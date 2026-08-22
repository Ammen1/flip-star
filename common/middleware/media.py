"""
Media delivery middleware.

Moved from ``api/middleware.py`` unchanged. Not currently registered in
``MIDDLEWARE`` -- nginx serves ``/media/`` directly in every deployed
configuration -- but retained because local development without nginx relies on
Django serving video with range-request support.
"""

from __future__ import annotations

from django.utils.deprecation import MiddlewareMixin

VIDEO_CONTENT_TYPES = {
    '.mp4': 'video/mp4',
    '.webm': 'video/webm',
    '.ogg': 'video/ogg',
    '.mov': 'video/quicktime',
}


class VideoStreamingMiddleware(MiddlewareMixin):
    """Advertise range support and correct the content type for video files."""

    def process_response(self, request, response):
        if not request.path.startswith('/media/'):
            return response

        for suffix, content_type in VIDEO_CONTENT_TYPES.items():
            if request.path.endswith(suffix):
                response['Accept-Ranges'] = 'bytes'
                response['Cache-Control'] = 'no-cache'
                response['Content-Type'] = content_type
                break

        return response
