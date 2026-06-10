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
2. To pull changes:
   ```
   GET /api/meals?since=2026-05-12T03:14:00Z&limit=200
   ```
   Returns rows where `updated_at >= since` **or** `deleted_at >= since`.
   Soft-deleted meals appear with `deleted_at` set; apply the tombstone locally
   and remove the meal from the device store.
3. To delete (web or any client):
   ```
   DELETE /api/meals/{client-generated-UUID}
   ```
   Soft-delete only: the row stays in the database with `deleted_at` set to
   now. A plain `GET /api/meals` (no `since`) hides deleted meals.
4. To push a change (create or update):
   ```
   PUT /api/meals/{client-generated-UUID}
   Content-Type: application/json
   { ...full Meal payload... }
   ```
   The server treats `PUT` as an upsert by ID. Use the same UUID Core Data
   already assigned so reconciliation is trivial.
5. After a successful push, mark the Meal as synced locally by setting
   `lastSyncGUID` to the value the server returns.

`PUT /api/meals/{id}` on a previously deleted meal clears `deleted_at` (restore).

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

The server upserts by ID. To soft-delete, PUT with `is_removed: true`; the
server also sets `deleted_at` for sync tombstones.

### First-login bootstrap

If a user has no people at all, `GET /api/people` (without `since`)
auto-creates a default person named **"Me"** with `is_default: true`.
iOS may rely on this or POST its own default person before syncing meals.

Meals reference people via `person_id` on `PUT /api/meals/{id}`.

## `MealPhoto` upload flow

Photo bytes go **direct to Azure Blob Storage**, not through the API:

1. Client `POST /api/photos/upload-url` with photo metadata
   (width, height, sha256, byte sizes, the meal it belongs to).
2. Server creates the `meal_photos` row and returns a one-time SAS URL.
3. Client `PUT`s the JPEG bytes to that SAS URL directly.
4. (Optional) Client `PATCH /api/photos/{id}` to confirm upload.

To **download** photo bytes later (e.g. sync pull on iOS):

1. Client `GET /api/photos/{photo_id}/download-url`
2. Server returns `{ "download_url": "...", "expires_at": "..." }` — a
   short-lived read-only SAS URL for the blob named in `blob_name`.
3. Client `GET`s the JPEG bytes from `download_url` directly.

Inline web photos (`image_data_b64`, no `blob_name`) return `404` on this
endpoint; use `GET /api/photos/{photo_id}` for those instead.

The Swift `PhotoStore` already has all the bits it needs (sha256, width,
height, byte sizes) from the existing `PhotoNutritionGuesser` pipeline.

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
