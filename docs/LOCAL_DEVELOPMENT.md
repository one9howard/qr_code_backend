# Local Development Manual

This guide explains how to run, test, and develop the InSite Signs application locally using Docker. This setup mimics the production environment (Railway) but allows for faster iteration.

## 1. Prerequisites
- **Docker Desktop** installed and running.
- **Git** installed.
- **PowerShell** or Command Prompt.

## 2. Quick Start (Run the App)

To start the application and database:

```powershell
# Start everything in the background (detached mode)
docker-compose up -d
```

Once running, access the app at:
👉 **[http://localhost:5000](http://localhost:5000)**

### Other Common Commands

| Goal | Command |
| :--- | :--- |
| **Stop everything** | `docker-compose down` |
| **View Logs** | `docker-compose logs -f` (Ctrl+C to exit) |
| **View logs for web only** | `docker-compose logs -f web` |
| **Rebuild** (if you added requirements) | `docker-compose up -d --build` |

---

## 3. Development Workflow

### Editing Code
Your local folder is "mounted" into the container. This means:
- **Routes/Python Files**: Changes apply immediately (Flask reloads automatically).
- **Templates/HTML**: Changes apply immediately (refresh browser).
- **CSS/JS**: Changes apply immediately (refresh browser).

### Adding New Libraries
If you modify `requirements.txt`, you **must** rebuild the container for it to pick up the new package:

```powershell
docker-compose build web
docker-compose up -d
```

---

## 4. Running Tests

You can run the test suite inside the container to ensure everything works before pushing.

### Option A: Run All Tests
```powershell
docker-compose exec web pytest
```
*Note: This runs the tests inside the running `web` container.*

### Option B: Run Specific Tests
```powershell
# Run only feature flows
docker-compose exec web pytest tests/test_feature_flows.py

# Run with verbose output
docker-compose exec web pytest -v
```

### Option C: Run with "Quiet" Mode (Fast)
```powershell
docker-compose exec web pytest -q
```

---

## 5. Troubleshooting

**Q: "Connection refused" to database?**
A: Ensure the database container is healthy:
```powershell
docker ps
```
If `insite_signs-db-1` keeps restarting, check logs: `docker logs insite_signs-db-1`.

**Q: Changes not showing up?**
A: Refresh your browser hard (Ctrl+Shift+R). If it's Python code, check the logs to see if Flask crashed due to a syntax error:
```powershell
docker-compose logs -f web
```

**Q: How do I start fresh?**
A: To wipe the database and start over:
```powershell
docker-compose down -v
docker-compose up -d
```
*(The `-v` flag deletes the database volume).*
