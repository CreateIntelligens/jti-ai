# JTAI Frontend

React/Vite frontend for the JTAI multi-app chat platform. The frontend serves:

- `/` general knowledge-base chat and admin panels
- `/jti` JTI assistant, quiz, knowledge, prompt, and history UI
- `/hciot` HCIoT hospital education assistant, knowledge workspace, topics, images, and prompt UI

## Requirements

- Node 20+
- pnpm 9.15+

The root Docker setup runs this app through the frontend container and nginx. For local frontend-only work:

```bash
pnpm install
pnpm dev
```

Useful scripts:

```bash
pnpm build
pnpm lint
pnpm test
pnpm exec tsc --noEmit
```

## Environment

The Docker compose file sets these for the frontend container:

```env
VITE_API_URL=http://localhost:${PORT:-8008}
VITE_PUBLIC_ALLOWED_PAGES=jti
VITE_PUBLIC_RESTRICTED_HOSTS=
```

For local development outside Docker, create a local env file if you need to point at a different backend:

```env
VITE_API_URL=http://localhost:8008
```

## Structure

```text
src/
├── pages/                 # Route-level app pages
├── components/            # Shared and app-specific UI
├── components/hciot/      # HCIoT workspace and operator docs
├── components/jti/        # JTI settings, quiz, and knowledge UI
├── services/api/          # Typed API clients
├── hooks/                 # Shared frontend hooks
├── styles/                # App-specific and shared CSS
└── locales/               # i18n strings

tests/
├── hciot/                 # HCIoT component and API-path tests
└── *.test.ts              # Shared app tests
```

Use `pnpm` for all frontend package and script operations.
