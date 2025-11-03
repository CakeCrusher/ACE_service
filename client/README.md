# ACE Service Client

React-based client application for visualizing the ACE service database and testing the API.

## Features

- **Playbooks View**: Browse and view all playbooks
- **Playbook Detail**: View individual playbooks with their bullets and metadata
- **Playground**:
  - Embed prompts with playbook context
  - Run learn workflows with customizable inputs

## Development

### Prerequisites

- Node.js 18+ and npm

### Setup

```bash
cd client
npm install
```

### Run Development Server

```bash
npm run dev
```

The client will be available at `http://localhost:3000`

## Building for Production

```bash
npm run build
```

The built files will be in the `dist/` directory, ready to be served by a web server.

## Environment Variables

Create a `.env` file in the client directory:

```
VITE_API_URL=http://localhost:8000
```

## Usage

1. **View Playbooks**: Navigate to the home page to see all playbooks in the system
2. **View Playbook Details**: Click on any playbook to see its bullets and metadata
3. **Embed Prompt**: Go to Playground to embed a prompt with playbook context
4. **Run Learn Workflow**: Use the Playground to start a learn workflow and monitor its progress
