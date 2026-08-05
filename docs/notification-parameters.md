# Notification Parameters

## Purpose

Defines the notification settings shared between the UI and the backend scheduler.

## Parameters

| Name | Type | Description |
|------|------|-------------|
| email | string | Email address for notifications |
| phone_number | string | Phone number for WhatsApp notifications |
| channel | string | Notification channel (`email` or `whatsapp`) |
| frequency | string | Notification frequency (`daily`) |
| relevance_threshold | float | Minimum match score required before notifying the user |

## Backend Behavior

The scheduler reads these settings from the database.

For each scheduled run:

- Read the user's notification settings.
- Check for new job matches.
- Filter matches whose score is greater than or equal to `relevance_threshold`.
- Send the notification using the selected `channel`.

## Development

The scheduler should support a configurable test interval (for example every 2 or 5 minutes) instead of waiting until the daily schedule.