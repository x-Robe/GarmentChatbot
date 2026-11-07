# Existing Catalog Assets and Hosting

The feature branch preserves the existing GitHub repository’s **1,993 JPEGs at data/images/tshirt/**. No JPEG was copied from the release or another local dataset, moved, rewritten or generated. All filenames and SHA-256 values match both remote main and CATALOG_ASSET_MANIFEST.csv. Existing total: 378,919,404 bytes (361.37 MiB). Existing public inclusion is not a new verification of redistribution/hosting rights; the owner must confirm those rights. Git LFS does not grant a license.

## Single-location resolution

backend/src/asset_paths.py defines BACKEND_ROOT as backend/ and IMAGE_ROOT as repository-root data/images/. Unchanged Qdrant paths data/images/tshirt/<id>.jpg resolve against repository root. Other relative file inputs remain backend-relative. api.image_url_for validates containment/traversal using the same allowed image root, and /images/tshirt/<id>.jpg stays unchanged. StaticFiles does not follow symlinks. No backend/data/images duplicate or symlink is created. ProductSearch query-image paths, ingestion and evaluation/validation path helpers use this convention. Backend schemas and product lists stay in backend/data.

Qdrant holds vectors/payloads, not JPEG binaries. The root catalog must accompany the host/deployment volume; moving just backend/ without the root data/images directory breaks image mounting. The host may use an authorized private asset package or existing repository checkout, but no public download URL or new image host is invented here.

## Metadata and missing files

Current backend/data/products.csv and products.json contain 2,000 entries; IDs 357–363 have no JPEG in the original repository. These seven files were not invented. root data/products.csv/json and sample metadata are retained unchanged as legacy owner material; active backend schema/list paths are under backend/data. models/fashion_clip.py is also retained pending owner review and is not the active encoder. See INTEGRATION_REPORT.md for every removed/superseded path.

CATALOG_ASSET_MANIFEST.csv contains 1,993 filenames/bytes/hashes. CATALOG_ASSET_SUMMARY.json distinguishes the clean release’s omission from this integration’s preserved repository assets. No Qdrant mutation/re-ingestion, embedding rebuild or model cache copying occurred. FashionCLIP/MiniLM weights, valid rotated credentials and compatible populated collection remain external. The hosting owner must confirm model and asset license terms.
