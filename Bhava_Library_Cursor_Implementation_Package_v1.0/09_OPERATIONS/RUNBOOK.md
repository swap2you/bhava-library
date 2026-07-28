# Operations Runbook

## Initial setup

```powershell
git init
.\bhava.ps1 bootstrap
.\bhava.ps1 doctor
```

## First core acquisition

```powershell
.\bhava.ps1 scan
.\bhava.ps1 estimate --profile core
.\bhava.ps1 acquire --profile core
.\bhava.ps1 verify
.\bhava.ps1 index
.\bhava.ps1 report
```

## Continue later

```powershell
.\bhava.ps1 resume
```

## Status

```powershell
.\bhava.ps1 status
```

## Update source

```powershell
.\bhava.ps1 scan
.\bhava.ps1 estimate --profile core --changes-only
.\bhava.ps1 acquire --profile core --changes-only
```

## Audio later

```powershell
.\bhava.ps1 estimate --profile audio
.\bhava.ps1 acquire --profile audio
```

Audio remains off until the owner invokes it.

## Video later

```powershell
.\bhava.ps1 estimate --profile video
.\bhava.ps1 acquire --profile video
```

## Backup

```powershell
.\bhava.ps1 backup --target "E:\BhavaLibraryBackup"
.\bhava.ps1 restore-check --target "E:\BhavaLibraryBackup"
```

## Original publication record

```powershell
.\bhava.ps1 copyright new-work
.\bhava.ps1 copyright notice --work-id BHAVA-WORK-YYYY-NNN
.\bhava.ps1 copyright freeze --work-id BHAVA-WORK-YYYY-NNN
```

## Never do

- `git add data`
- move originals into public web folders
- edit an original PDF
- delete `.part` files before checking job state
- use a destructive backup mirror without a separate verified copy
- enable audio/video during the first core acquisition
