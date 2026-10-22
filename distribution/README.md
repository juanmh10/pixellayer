# Release operations

Only distribution automation is stored here. The existing Python source tree is
historical; the native Windows download is built separately. No private source
checkout, GitHub PAT, Google service-account key or model weights are needed by CD.

1. A maintainer verifies the approved build and prepares the public package,
   excluding internal documents and the separately distributed skill.
2. Commit `distribution/manifests/VERSION.json`, recording the exact archive,
   size, SHA-256 and engine commit, after reviewing the package contents.
3. Create a draft release `vVERSION`, targeted at the reviewed distribution
   commit. Upload exactly the Windows ZIP and its `.sha256` file.
4. Run **Publish Windows release** on `main`, with `version=VERSION`.
5. CD checks the committed approval, package inventory, per-file hashes,
   Windows target and matching source provenance before authenticating to Google.
6. CD uploads immutable files to GCS, checks anonymous HTTPS downloads, adds the
   release JSON to GitHub, publishes the release, verifies the GitHub ZIP, then
   updates `channels/stable.json` last. Same-content retries are supported;
   changing an existing version's contents is rejected. Older releases cannot
   replace the current stable version through this workflow.

GCP project: `website-prod-juan`; region: `us-central1`.
Download bucket: `pixellayer-prod-downloads-website-prod-juan`.
Skill bucket: `pixellayer-prod-skills-website-prod-juan` (private, not used by CD).
Download base: https://storage.googleapis.com/pixellayer-prod-downloads-website-prod-juan
No custom-domain HTTPS or load balancer is configured.

## Access and publication

The GitHub OIDC provider accepts only this repository's numeric identity, main
branch, workflow_dispatch event and `.github/workflows/publish-windows.yml`.
The dedicated `pixellayer-prod-publisher` service account has object access only
on the download bucket. Google credentials are short-lived and removed by the
auth action. GitHub's job token publishes releases in this repository only.
Public files and workflow logs must never contain private source or credentials.

Versioned archives, checksum files and release JSON have immutable content.
The stable manifest uses short cache lifetime. Clients verify SHA-256, and must
stop on integrity failure rather than retry from a different host.

## Retention

`lifecycle.json` deletes prereleases after 30 days and retired stable objects
180 days after their Custom-Time retirement timestamp. Publication protects the
three newest stable releases (including current stable and rollback) with
Temporary Hold. When a release leaves that set, its objects receive Custom-Time
and their hold is removed. A restored release may retain an older retirement timestamp; its hold prevents deletion.

Bucket Object Versioning is disabled; seven-day soft delete permits recovery
from accidental deletion and incurs storage charges. GitHub stable release assets
remain available independently. Lifecycle deletion is asynchronous, not immediate.
No private staging files belong in the public download bucket.

## Rollback and recovery

If publication fails before stable.json is updated, the prior channel remains
selected; inspect the run and retry with the same approved bytes. An initial
publication may leave public versioned GCS files even if GitHub publication fails.

To roll back, download a previously approved release.json from GitHub, verify
its packages on both origins, put its GCS objects on Temporary Hold, and replace
channels/stable.json with that exact manifest using a generation precondition.
Perform rollback as an explicit maintainer operation; publication rejects downgrades.
Retain the displaced version for investigation or withdraw it explicitly.

To revoke CD, disable the `pixellayer-prod-publication` identity provider and
remove the publisher's download-bucket object binding. To stop anonymous access,
remove `allUsers`/`roles/storage.objectViewer` from the download bucket. Neither
operation deletes data. Infrastructure recreation requires separately authorized
GCP changes; the publication workflow cannot edit IAM or bucket settings.

## Test candidates

The same workflow accepts an approved ID such as `0.5.1-candidate.1`. The package's
engine version remains `0.5.1`; the ID names this particular immutable test bundle.
Create its draft GitHub release as a **prerelease**, targeted at the reviewed
public distribution commit. Candidate assets go under `prereleases/ID/`; their
manifest is mirrored to `channels/candidate.json`. The manifest declares testing
only, expiry after 30 days and pending antivirus acceptance. Candidate objects
have no Temporary Hold, allowing the existing 30-day lifecycle rule to apply.

Candidate publication never runs stable retention or writes stable.json, and
publishes the GitHub prerelease with latest=false. The stable generation is
checked before and after publication. GitHub's latest stable remains unchanged.
Do not use a candidate implicitly for a normal stable installation. The test
skill or explicit user request must select the exact candidate ID.

To withdraw a candidate, remove its channel pointer using the current generation
as a precondition and mark its GitHub prerelease as withdrawn/draft. Leave stable
untouched. Versioned candidates are immutable and expire from GCS after 30 days;
GitHub may retain them for diagnosis. Do not overwrite a candidate ID for a new
bundle: publish candidate.2 instead. Skill and private source are not published.
