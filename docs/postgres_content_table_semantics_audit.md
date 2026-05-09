# PostgreSQL Content Table Semantics Audit

## Latest Dedup Run

- mode: apply
- strategy: keep the maximum identity `id` in each logical duplicate group

| Table | Key | Duplicate Groups | Duplicate Rows | Rows To Delete | Deleted |
| --- | --- | ---: | ---: | ---: | ---: |
| `talks` | `topic_id` | 2491 | 18204 | 15713 | 15713 |
| `questions` | `topic_id` | 0 | 0 | 0 | 0 |
| `answers` | `topic_id` | 0 | 0 | 0 | 0 |
| `articles` | `topic_id` | 0 | 0 | 0 | 0 |
| `latest_likes` | `topic_id, owner_user_id, create_time` | 359 | 2374 | 2015 | 2015 |
| `like_emojis` | `topic_id, emoji_key` | 343 | 2264 | 1921 | 1921 |
| `user_liked_emojis` | `topic_id, emoji_key` | 0 | 0 | 0 | 0 |

## Top Duplicate Samples

### talks

No duplicate groups.

### questions

No duplicate groups.

### answers

No duplicate groups.

### articles

No duplicate groups.

### latest_likes

No duplicate groups.

### like_emojis

No duplicate groups.

### user_liked_emojis

No duplicate groups.

## Intended Semantics

- `talks`, `questions`, `answers`, and `articles` have one logical row per `topic_id`.
- `latest_likes` is the current latest-like snapshot keyed by `(topic_id, owner_user_id, create_time)`.
- `like_emojis` and `user_liked_emojis` are keyed by `(topic_id, emoji_key)`.
- `likes` remains an append/history table and is intentionally excluded.
