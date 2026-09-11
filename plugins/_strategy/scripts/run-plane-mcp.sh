#!/bin/sh
set -eu

: "${PLANE_API_KEY:?PLANE_API_KEY is required}"
: "${PLANE_WORKSPACE_SLUG:?PLANE_WORKSPACE_SLUG is required}"
: "${PLANE_BASE_URL:?PLANE_BASE_URL is required}"

exec uvx plane-mcp-server stdio
