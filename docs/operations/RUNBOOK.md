# Operations Runbook

```powershell
.\bhava.ps1 bootstrap
.\bhava.ps1 doctor
.\bhava.ps1 scan
.\bhava.ps1 resolve
.\bhava.ps1 estimate --profile core
.\bhava.ps1 acquire --profile core
.\bhava.ps1 verify
.\bhava.ps1 index
.\bhava.ps1 report
.\bhava.ps1 resume
.\bhava.ps1 backup --target "E:\BhavaLibraryBackup"
```

Exit codes: 0 success, 10 partial, 20 disk guard, 21 network, 22 source drift, 23 access, 24 integrity, 25 config, 26 backup verify, 30 internal.
