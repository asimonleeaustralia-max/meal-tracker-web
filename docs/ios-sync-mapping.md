# iOS ↔ Web sync field mapping

The web backend's `meal-service` was designed to be the cloud counterpart of
the MealTracker iOS Core Data store. Field names line up 1:1 between Swift
(camelCase) and Python/SQL (snake_case).

## Entity map

| Swift @objc class | Web SQL table | Web API path        |
|-------------------|---------------|---------------------|
| `Meal`            | `meal.meals`  | `/api/meals`        |
| `Person`          | `meal.people` | `/api/people`       |
| `MealPhoto`       | `meal.meal_photos` | `/api/photos`  |

## `Meal` field map

Every numeric attribute on the Swift `Meal` Core Data entity (`calories`,
`carbohydrates`, `protein`, …) has a matching column with the same name in
snake_case. Every `*IsGuess` boolean has a `*_is_guess` column.

| Swift               | SQL / JSON               |
|---------------------|--------------------------|
| `id`                | `id` (UUID)              |
| `title`             | `title`                  |
| `date`              | `date` (ISO 8601 UTC)    |
| `latitude`          | `latitude`               |
| `longitude`         | `longitude`              |
| `calories`          | `calories`               |
| `caloriesIsGuess`   | `calories_is_guess`      |
| `carbohydrates`     | `carbohydrates`          |
| `carbohydratesIsGuess` | `carbohydrates_is_guess` |
| `monounsaturatedFat`| `monounsaturated_fat`    |
| `a2BetaCasein`      | `a2_beta_casein`         |
| `vitaminA` … `vitaminK` | `vitamin_a` … `vitamin_k` |
| `lastSyncGUID`      | `last_sync_guid`         |
| `photoGuesserType`  | `photo_guesser_type`     |
| `productName`       | `product_name`           |

Plus extra server-managed columns the iOS app shouldn't try to set:
`user_id`, `created_at`, `updated_at`, `deleted_at`.

| Swift (suggested) | SQL / JSON   | Notes                          |
|-----------------|--------------|--------------------------------|
| `deletedAt`     | `deleted_at` | `null` = active; set = tombstone |

## Sync protocol (recommended)

Use a simple **last-write-wins, incremental pull** model:

1. Client stores the most recent `updated_at` it has seen.
2. To pull **all** entity types in one round-trip (preferred on iOS):
   ```
   GET /api/sync/changes?since=2026-05-12T03:14:00Z
   ```
   Returns `{ "meals": [...], "people": [...], "photos": [...], "server_time": "..." }`.
   Use `server_time` as the next cursor after applying changes locally.
3. Or pull per entity (three requests):
   ```
   GET /api/meals?since=2026-05-12T03:14:00Z&limit=200
   ```
   Returns rows where `updated_at >= since` **or** `deleted_at >= since`.
   Soft-deleted meals appear with `deleted_at` set; apply the tombstone locally
   and remove the meal from the device store.
4. To delete (web or any client):
   ```
   DELETE /api/meals/{client-generated-UUID}
   ```
   Soft-delete only: the row stays in the database with `deleted_at` set to
   now. A plain `GET /api/meals` (no `since`) hides deleted meals.
5. To push a change (create or update):
   ```
   PUT /api/meals/{client-generated-UUID}
   Content-Type: application/json
   { ...full Meal payload... }
   ```
   The server treats `PUT` as an upsert by ID. Use the same UUID Core Data
   already assigned so reconciliation is trivial.
6. After a successful push, mark the Meal as synced locally by setting
   `lastSyncGUID` to the value the server returns. The server **always**
   generates a new `last_sync_guid` (and bumps `updated_at`) on every
   `POST /api/meals` and `PUT /api/meals/{id}` — clients must not rely on
   sending their own sync marker.

`PUT /api/meals/{id}` on a previously deleted meal clears `deleted_at` (restore).

`person_id` on create/update must reference a `Person` owned by the same
user; otherwise the server returns `400`.

For a more robust model later (concurrent edits on multiple devices),
consider adding a `version` integer that clients must include in PUTs.

## `Person` sync

`Person` uses the same incremental pull + PUT-by-UUID push model as `Meal`.

| Swift            | SQL / JSON            |
|------------------|-----------------------|
| `id`             | `id` (UUID)           |
| `name`           | `name`                |
| `isDefault`      | `is_default`          |
| `isRemoved`      | `is_removed`          |

Server-managed: `user_id`, `created_at`, `updated_at`, `deleted_at`.

### Pull

```
GET /api/people?since=2026-05-12T03:14:00Z
```

When `since` is set, the response includes rows where `updated_at >= since`
**or** `deleted_at >= since`. Removed people have `is_removed: true` and
`deleted_at` set so tombstones propagate to other devices. A plain
`GET /api/people` (no `since`) hides removed people.

### Push

```
PUT /api/people/{client-generated-UUID}
Content-Type: application/json
{ "name": "Simon", "is_default": true, "is_removed": false }
```

The server upserts by ID. To soft-delete, either PUT with `is_removed: true`
(the server also sets `deleted_at` for sync tombstones) or:

```
DELETE /api/people/{client-generated-UUID}
```

`DELETE` sets `is_removed: true`, bumps `updated_at`, and sets `deleted_at`.
Meals that referenced the deleted person are reassigned to the user's default
person (a new **"Me"** default is created if needed). The row is never
hard-deleted while meals still reference it.

### First-login bootstrap

If a user has no people at all, `GET /api/people` (without `since`)
auto-creates a default person named **"Me"** with `is_default: true`.
iOS may rely on this or POST its own default person before syncing meals.

Meals reference people via `person_id` on `PUT /api/meals/{id}`.

## `MealPhoto` sync

| Swift (suggested)   | SQL / JSON            | Notes                              |
|-------------------|-----------------------|------------------------------------|
| `id`              | `id` (UUID)           | Client-generated                   |
| `mealId`          | `meal_id`             | Parent meal                        |
| `width` / `height`| `width` / `height`    |                                    |
| `sha256`          | `sha256`              | Content hash of upload JPEG        |
| `byteSizeUpload`  | `byte_size_upload`    |                                    |
| `displayOrder`    | `display_order`       | Lower = first in meal            |
| `blobName`        | `blob_name`           | Azure path; set by upload-url      |

Server-managed: `user_id`, `created_at`, `updated_at`.

### Push (upload new photo via SAS)

Photo bytes go **direct to Azure Blob Storage**, not through the API:

1. `POST /api/photos/upload-url` with metadata (`meal_id`, width, height,
   sha256, byte sizes). Server creates the `meal_photos` row, sets
   `blob_name`, and returns `{ photo_id, blob_name, upload_url, expires_at }`.
2. Client `PUT`s the JPEG bytes to `upload_url` (Azure SAS).
3. `PATCH /api/photos/{photo_id}` with optional `byte_size_upload`, `sha256`,
   `display_order` to confirm upload complete. Server bumps `updated_at`.

Optional metadata-only upsert (e.g. reorder or fix fields without re-upload):

```
PUT /api/photos/{client-generated-UUID}
Content-Type: application/json
{ "meal_id": "...", "width": 1080, "height": 1080, "display_order": 0, ... }
```

No image bytes on PUT — use the SAS flow above for JPEG data.

### Pull (incremental metadata)

```
GET /api/photos?since=2026-05-12T03:14:00Z
```

Returns all photos for the user where `updated_at >= since`. Responses omit
`image_data_b64` (metadata only). Each row includes `blob_name` so the client
knows which blob to fetch.

Store the highest `updated_at` from the response as the next `since` cursor.

### Download photo bytes

After metadata pull, fetch bytes per photo:

1. `GET /api/photos/{photo_id}/download-url`
2. Server returns `{ "download_url": "...", "expires_at": "..." }` — a
   short-lived read-only SAS URL for `blob_name`.
3. Client `GET`s the JPEG from `download_url`.

Inline web photos (`image_data_b64`, no `blob_name`) return `404` on
download-url; use `GET /api/photos/{photo_id}` for those instead.

The Swift `PhotoStore` already has the metadata fields (sha256, width, height,
byte sizes) from the existing `PhotoNutritionGuesser` pipeline.

## Codable hint for the iOS side

In `MealCloudDTO.swift` (suggested new file), set `CodingKeys` so Codable
handles the camelCase↔snake_case conversion automatically — or set
`JSONDecoder.keyDecodingStrategy = .convertFromSnakeCase` on your shared
decoder and you can drop the keys entirely:

```swift
let decoder = JSONDecoder()
decoder.keyDecodingStrategy = .convertFromSnakeCase
decoder.dateDecodingStrategy = .iso8601

let encoder = JSONEncoder()
encoder.keyEncodingStrategy = .convertToSnakeCase
encoder.dateEncodingStrategy = .iso8601
```

The one exception is fields like `a2BetaCasein` where the camelCase has
adjacent digit+letter pairs — Foundation will still convert these correctly
(`a2BetaCasein` ↔ `a2_beta_casein`).
