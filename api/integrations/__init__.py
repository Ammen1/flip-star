"""External provider clients.

Each sub-package owns one provider: its HTTP/SOAP transport, credential
handling, request signing, response parsing and error mapping. Business logic
must not construct provider requests directly -- it calls into these clients.
"""
