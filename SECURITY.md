# Security and integrity reports

This repository holds research documents, draft benchmark specifications and the
pipeline that publishes them. It contains no production systems, no credentials
and no customer data.

## What to report

- A credential, personal data or private infrastructure detail found anywhere in
  this repository or its history.
- A published file whose SHA-256 digest does not match `SHA256SUMS`, the GitHub
  release or the archival record.
- A vulnerability in the publication pipeline (`tools/`) or in the workflows
  (`.github/workflows/`).

## How to report

Use GitHub private vulnerability reporting: **Security → Report a vulnerability**
on this repository. Please do not open a public issue for a suspected secret.

## Verifying a published note

```bash
# in a directory holding the downloaded release files
sha256sum -c SHA256SUMS

# attestation of an immutable GitHub release (any version tag, e.g. v1.0 or v1.1)
gh release verify research-note-001-v1.1 -R M12-pixel1/margelis-research
gh release verify-asset research-note-001-v1.1 Margelis_Research_Note_001.pdf -R M12-pixel1/margelis-research

# rebuild the PDF from source and compare it with the published digest
python -m pip install --require-hashes -r tools/requirements.lock
python tools/publish.py verify 001 --rebuild
```

## Safeguards in place

- `python tools/publish.py check` scans every publishable file for credentials,
  private file-system paths, internal host names, IP addresses, e-mail addresses
  and phone numbers, and the `validate` workflow runs it on every push.
- GitHub secret scanning with push protection and Dependabot alerts are enabled
  for this repository; `main` accepts changes only through pull requests that
  pass `validate`, and releases are immutable.
- Python dependencies are installed with `--require-hashes` from
  `tools/requirements.lock`, so a substituted package cannot be installed silently.
- The Zenodo token is read only from the `ZENODO_ACCESS_TOKEN` environment
  variable or repository secret and is never written to disk or printed.
