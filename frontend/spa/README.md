# Frontend SPA

Vue 3 + TypeScript single-page application with Vite.

## Prerequisites

- Node.js 20
- pnpm 8.15.8

## Setup

This project uses pnpm 8.15.8. The `packageManager` field in `package.json` ensures that the same version is used in both local development and CI.

To install dependencies:

```bash
pnpm install
```

Note: If you have Corepack enabled (Node.js 16.9+), the correct pnpm version will be automatically selected based on the `packageManager` field. Otherwise, install pnpm 8.15.8 manually:

```bash
corepack enable
corepack prepare pnpm@8.15.8 --activate
```

## Development

Start the development server:

```bash
pnpm dev
```

The application will be available at [http://localhost:5173](http://localhost:5173).

## Scripts

| Command               | Description                                   |
| --------------------- | --------------------------------------------- |
| `pnpm dev`            | Start development server                      |
| `pnpm build`          | Build for production                          |
| `pnpm preview`        | Preview production build                      |
| `pnpm lint`           | Run all linters (ESLint, Stylelint, Prettier) |
| `pnpm lint:js`        | Run ESLint                                    |
| `pnpm lint:style`     | Run Stylelint                                 |
| `pnpm lint:style:fix` | Fix Stylelint issues                          |
| `pnpm format`         | Format code with Prettier                     |
| `pnpm format:check`   | Check Prettier formatting                     |
| `pnpm typecheck`      | Run TypeScript type checks                    |
| `pnpm test`           | Run unit tests                                |
| `pnpm test:unit`      | Run unit tests in watch mode                  |
| `pnpm test:coverage`  | Run tests with coverage report                |
| `pnpm test:e2e`       | Run end-to-end tests                          |
| `pnpm check`          | Run all checks (lint, typecheck, test)        |

## Tech Stack

- **Framework**: Vue 3 with Composition API
- **Build Tool**: Vite 4
- **Language**: TypeScript 5
- **State Management**: Pinia 2
- **Routing**: Vue Router 4
- **HTTP Client**: Axios
- **Testing**: Vitest, Testing Library, Playwright
- **Linting**: ESLint, Stylelint
- **Formatting**: Prettier
- **CSS**: PostCSS with nesting support

## Project Structure

- `src/`: Application source code
  - `components/`: Reusable Vue components
  - `views/`: Page components
  - `router/`: Vue Router configuration
  - `stores/`: Pinia stores
  - `types/`: TypeScript type definitions
- `tests/`: Test files
- `public/`: Static assets

## CI/CD

The project is configured for GitHub Actions CI with the following checks:

- Linting (ESLint, Stylelint, Prettier)
- Type checking (TypeScript)
- Unit tests with coverage (>80% required)

All frontend CI jobs use pnpm 8.15.8 with frozen lockfile to ensure dependency consistency.

**Note**: The CI coverage check requires `coverage/coverage-summary.json` to be generated. This is configured via the `json-summary` reporter in `vitest.config.ts`.
