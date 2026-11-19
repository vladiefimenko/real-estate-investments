# Deploying Axiom for free (Render + Neon)

This puts the whole platform on a public `https://….onrender.com` address at no cost:

* **Render** (free web service) runs the app. `render.yaml` and `Dockerfile.render` package the
  API and the web app into one container, so there is a single URL.
* **Neon** (free PostgreSQL) stores all data. Render's own free database is deleted after 30 days,
  Neon's free tier is not.
* Uploaded documents are stored encrypted **in the database** (`AXIOM_STORAGE_BACKEND=database`),
  because free Render services have no persistent disk.

## 1. Create the database (Neon)

1. Go to <https://neon.tech> and sign up (the **Continue with GitHub** button is easiest).
2. Create a project: any name (e.g. `axiom`), Postgres **16**, region **AWS US West 2 (Oregon)**
   (same region as the Render service).
3. On the project dashboard click **Connect**. Turn **Connection pooling off**, then copy the
   connection string. It looks like
   `postgresql://user:password@ep-xxxx.us-west-2.aws.neon.tech/neondb?sslmode=require`.
   Keep it private: it contains the database password.

## 2. Create the app (Render)

1. Go to <https://render.com> and sign up with **GitHub**.
2. Click **New** → **Blueprint**. Connect your GitHub account if asked and give Render access to
   the `real-estate-investments` repository.
3. Select the repository. Render reads `render.yaml` and shows one service, **axiom** (Free).
4. When it asks for **AXIOM_DATABASE_URL**, paste the Neon connection string from step 1.
5. Click **Deploy Blueprint**. The first build takes about 5–10 minutes.
6. When the service shows **Live**, open its URL (top of the service page), go to `/register` and
   create your workspace.

From then on, every merge to `main` redeploys automatically.

## What to expect on the free tier

* After **15 minutes without visitors** the service goes to sleep. The next visit takes about a
  minute to wake it up; after that it is fast again. Your data is safe in Neon either way.
* One free service fits within Render's monthly free hours even if it never sleeps.
* Neon's free tier includes 0.5 GB of storage, which holds a lot of deals and documents.
* Anyone with the URL can create their own, separate workspace. They cannot see yours.

## Optional settings (Render → service → Environment)

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables AI extraction and the AI analyst. Without it the rule-based fallback is used. |
| `AXIOM_SEED_DEMO_ON_REGISTER=false` | Stop offering the five demo deals to new workspaces. |

Do not change `AXIOM_SECRET_KEY` after the first deploy: it signs logins and encrypts the stored
documents, so changing it would make existing uploads unreadable.
