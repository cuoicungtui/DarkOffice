# Strategy API

## Purpose

Routes authenticated, CSRF-protected browser calls to the bundled Strategy service.

## Contract

`POST /api/strategy` accepts an `action` such as `dashboard`, `create_node`,
`checkin`, or `sync`. Domain validation and persistence remain in
`plugins/_strategy`; this module intentionally owns no business logic.

## Verification

Run the focused strategy tests and call the dashboard endpoint while logged in.
