# Demo Context — Notification Preferences

## Problem

Users of this application currently receive every notification by email,
with no way to opt out of individual categories. Support tickets about
"too many emails" have become a recurring complaint.

## Solution

Let users manage which notification categories they receive by email from a
single settings page, with sane defaults for new accounts.

## Business context

Reducing unwanted email volume is expected to lower unsubscribe/spam-report
rates and reduce support load.

## Features

### Notification preferences center

Users can view and toggle, per category (`account`, `billing`, `product
updates`, `marketing`), whether they receive that category by email.
Toggling a category off must take effect for the next notification sent,
not retroactively.

Acceptance criteria:

- Given a logged-in user, when they open the notification settings page,
  then they see one toggle per category with its current state.
- Given a user turns a category off, when a notification of that category
  is triggered afterwards, then no email is sent for it.
- Given a new account is created, when it is first provisioned, then
  `account` and `billing` default to on and `marketing` defaults to off.

### Digest fallback

Users who disable a category can instead choose to receive a weekly digest
summarizing what they missed, opt-in, off by default.

Acceptance criteria:

- Given a user has disabled `product updates` emails, when they enable the
  weekly digest option, then they receive at most one digest email per week
  covering that category.

## Non-goals

- Push notifications and SMS are out of scope for this feature set.

## Dependencies

- The digest fallback feature depends on the notification preferences
  center existing first (it reads per-category state).

## Testing requirements

- Unit tests for preference toggling logic.
- Integration test verifying a disabled category suppresses the
  corresponding email send.

## Definition of Done

- All acceptance criteria above are implemented and covered by automated
  tests, and the settings page is reachable from account settings.
