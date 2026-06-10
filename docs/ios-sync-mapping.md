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
`user_id`, `created_at`, `updated_at`.

## Sync protocol (recommended)

Use a simple **last-write-wins, incremental pull** model:

1. Client stores the most recent `updated_at` it has seen.
2. To pull changes:
   ```
   GET /api/meals?since=2026-05-12T03:14:00Z&limit=200
   ```
3. To push a change (create or update):
   ```
   PUT /api/meals/{client-generated-UUID}
   Content-Type: application/json
   { ...full Meal payload... }
   ```
   The server treats `PUT` as an upsert by ID. Use the same UUID Core Data
   already assigned so reconciliation is trivial.
4. After a successful push, mark the Meal as synced locally by setting
   `lastSyncGUID` to the value the server returns.

For a more robust model later (concurrent edits on multiple devices),
consider adding a `version` integer that clients must include in PUTs.

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
