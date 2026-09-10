# plane_webhook.py DOX

## Purpose

Receives authenticated Plane webhook deliveries and persists them to the strategy sync inbox.

## Contract

`POST /api/plane_webhook` does not use browser authentication or CSRF. It requires the HMAC-SHA256 `X-Plane-Signature`, validates the configured workspace, and acknowledges a durably stored delivery. The job-loop worker processes the payload asynchronously.

## Verification

Test valid signatures, invalid signatures, duplicate deliveries, malformed JSON, and an unknown workspace.
