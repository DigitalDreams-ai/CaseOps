# Nightly Pre-Compute Setup

**Schedule:** Weekdays (Mon-Fri) at 6:00 AM MST

## Option 1: Windows Task Scheduler (Recommended)

### Setup

1. **Open Task Scheduler**
   - Windows key → "Task Scheduler" → Open

2. **Create Basic Task**
   - Right-click "Task Scheduler Library" → "Create Basic Task..."
   - Name: `CaseOps Nightly Pre-Compute`
   - Description: `Generate investigation records for all active issues`

3. **Set Trigger**
   - Trigger: "Daily"
   - Start: Today at 6:00 AM
   - Recur every: 1 day
   - Click "Advanced settings"
     - ☑ Repeat task every: (disable, or use once daily)
     - ☑ Run only on Mon-Fri (set days)

4. **Set Action**
   - Action: "Start a program"
   - Program: `C:\Python311\python.exe` (or wherever Python is installed)
   - Add arguments: `C:\Users\sean\Projects\Salesforce\DigitalDreams\CaseOps\nightly_scheduler.py`
   - Start in: `C:\Users\sean\Projects\Salesforce\DigitalDreams\CaseOps`

5. **Set Conditions**
   - ☑ Run only when user is logged in (or uncheck for headless)
   - ☑ Wake the computer to run this task

6. **Finish**
   - Save task (may require admin password)

### Verify

- Check logs: `CaseOps/logs/nightly_precompute.log`
- Task Scheduler → Task Scheduler Library → Find "CaseOps Nightly Pre-Compute" → Right-click "Run" to test

---

## Option 2: Direct Scheduler Script

If you want the scheduler to run continuously:

```bash
cd C:\Users\sean\Projects\Salesforce\DigitalDreams\CaseOps
python nightly_scheduler.py
```

This will block (runs forever). Use with a process manager or Windows Service wrapper.

**Requires:** `pip install schedule`

---

## Option 3: Cron (WSL/Linux only)

If you have WSL or run on Linux:

```bash
# Edit crontab
crontab -e

# Add line (6 AM MST = 13:00 UTC, weekdays only)
0 13 * * 1-5 cd /path/to/CaseOps && python -c "from run_pipeline import run_nightly_precompute; run_nightly_precompute()"
```

---

## Verify Setup

Check logs after first run:

```
CaseOps/logs/nightly_precompute.log
```

Expected output:

```
2026-05-17 06:00:01 [INFO] Starting nightly pre-computation...
2026-05-17 06:15:30 [INFO] Pre-computation complete: 30 succeeded, 0 failed
```

---

## Disable

**Windows Task Scheduler:**
- Right-click task → "Disable"
- Or delete task entirely

**Scheduler script:**
- Stop the process (`Ctrl+C`)
