# Common Chronicle Frontend

A modern React TypeScript frontend for the Common Chronicle historical timeline generation platform.

## 🚀 Overview

This is the frontend application for Common Chronicle, an AI-powered historical research platform that transforms research questions into comprehensive timelines with verified sources. The frontend provides an intuitive interface for users to create research tasks, view generated timelines, and manage their historical research projects.

## 🛠 Tech Stack

- **Framework**: React 19.1.0 with TypeScript
- **Build Tool**: Vite 6.3.5
- **Styling**: Tailwind CSS 3.4.17
- **Routing**: React Router DOM 7.6.2
- **HTTP Client**: Axios 1.9.0
- **Icons**: Heroicons 2.2.0
- **State Management**: React Context API
- **Local Storage**: IndexedDB (via idb 8.0.3)
- **Code Quality**: ESLint + Prettier

## 🏗 Project Structure

```
src/
├── components/           # Reusable UI components
│   ├── Auth/            # Authentication modals
│   ├── ChronicleHeader.tsx
│   ├── Header.tsx       # Main navigation header
│   ├── InkBlotButton*.tsx # Styled button variants
│   ├── ParchmentPaper.tsx
│   ├── ProgressDisplay.tsx
│   ├── TaskForm.tsx
│   ├── TaskListPanel.tsx
│   ├── TimelineCard.tsx
│   ├── TimelineDisplay.tsx
│   ├── VerticalWavyLine.tsx
│   └── WavyLine.tsx
├── contexts/            # React Context providers
│   ├── auth.ts         # Authentication utilities
│   └── AuthContext.tsx # Auth state management
├── pages/              # Page components
│   ├── NewTaskPage.tsx     # Task creation page
│   ├── PublicTimelinesPage.tsx # Public timelines browser
│   └── TaskPage.tsx        # Individual task view
├── services/           # API and data services
│   ├── api.ts         # HTTP API client
│   └── indexedDB.service.ts # Local storage service
├── types/             # TypeScript type definitions
│   ├── db.types.ts    # Database/API types
│   └── index.ts       # Exported types
├── utils/             # Utility functions
│   ├── exportUtils.ts  # Timeline export utilities
│   └── timelineUtils.ts # Timeline processing utilities
└── App.tsx            # Main application component
```

## 🚀 Getting Started

### Prerequisites

- Node.js 18+
- npm or yarn package manager

### Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/your-org/Common_Chronicle.git
   cd Common_Chronicle/frontend
   ```

2. **Install dependencies**

   ```bash
   npm install
   # or
   yarn install
   ```

3. **Set up environment variables**

   Create a `.env` file in the frontend directory (optional - has intelligent defaults):

   ```env
   # For explicit API URL (optional)
   VITE_API_BASE_URL=http://localhost:8080

   # For development port (default: 8080)
   VITE_DEV_BACKEND_PORT=8080
   ```

### Development

1. **Start the development server**

   ```bash
   npm run dev
   # or
   yarn dev
   ```

2. **Open your browser**

   Navigate to `http://localhost:5173` (or the port shown in your terminal)

### Building for Production

```bash
npm run build
# or
yarn build
```

Built files will be in the `dist/` directory.

## 🎯 Key Features

### 📝 Timeline Creation

- **Research Question Input**: Natural language research questions
- **Data Source Selection**: Multiple historical data sources
- **Real-time Progress**: Live updates during AI processing
- **WebSocket Integration**: Real-time task status updates

### 🔍 Timeline Browsing

- **Public Archives**: Browse community-generated timelines
- **My Chronicles**: Personal timeline management
- **Search & Filter**: Find specific historical topics
- **Export Options**: Download timelines in various formats

### 🔐 User Management

- **Authentication**: Login/register system
- **Session Management**: Persistent login state
- **User Preferences**: Personalized experience
- **Task Ownership**: Private and public timeline options

### 📱 Responsive Design

- **Mobile-First**: Optimized for all screen sizes
- **Accessibility**: Screen reader friendly
- **Performance**: Optimized loading and rendering
- **Progressive Enhancement**: Works without JavaScript

## 🎨 UI Design System

### Theme

- **Color Scheme**: Parchment and scholar colors for historical feel
- **Typography**: Serif fonts for headers, sans-serif for body text
- **Visual Effects**: Ink blot animations, wavy lines, paper textures

### Components

- **InkBlotButton**: Animated buttons with ink spreading effect
- **ParchmentPaper**: Paper-textured containers
- **WavyLine**: Decorative separator elements
- **TimelineCard**: Event display cards with historical styling

## 🔧 Development Scripts

```bash
# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Run linting
npm run lint

# Fix linting issues
npm run lint:fix

# Format code
npm run format

# Check code formatting
npm run format:check
```

## 📡 API Integration

The frontend communicates with the backend through:

- **REST API**: CRUD operations for tasks and timelines
- **WebSocket**: Real-time updates during timeline generation
- **Authentication**: JWT-based authentication
- **Error Handling**: Comprehensive error boundaries and user feedback

### API Configuration

The app intelligently detects the environment and builds URLs accordingly:

- **Domain Access**: `[domain]` → `https://[domain]/api` (no port)
- **IP Access**: `192.168.1.100` → `http://192.168.1.100:8080/api` (with port)
- **Local Development**: `localhost` → `http://localhost:8080/api` (with port)

## 💾 Data Management

### Local Storage

- **IndexedDB**: Caches completed timelines for offline viewing
- **Session Storage**: Temporary UI state
- **LocalStorage**: Authentication tokens and user preferences

### State Management

- **React Context**: Global authentication and user state
- **Component State**: Local UI state and form handling
- **Stale-While-Revalidate**: Optimistic updates with background refresh

## 🧪 Testing

```bash
# Run unit tests (when available)
npm test

# Run e2e tests (when available)
npm run test:e2e
```

## 🔒 Security

- **CSP Headers**: Content Security Policy for XSS protection
- **HTTPS**: All production traffic encrypted
- **Token Management**: Secure JWT storage and refresh
- **Input Validation**: Client-side validation with server-side verification

## 🌍 Deployment

### Environment Variables

```bash
cp .env.example .env
# edit your .env
```

### Build Commands

```bash
# Install dependencies
npm ci

# Build for production
npm run build

# Serve static files from dist/
```

## 🤝 Contributing

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Commit changes**: `git commit -m 'Add amazing feature'`
4. **Push to branch**: `git push origin feature/amazing-feature`
5. **Open a Pull Request**

### Code Style

- **ESLint**: Enforced linting rules
- **Prettier**: Consistent code formatting
- **TypeScript**: Strong typing for better code quality
- **Conventional Commits**: Standardized commit messages

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](../LICENSE) file for details.

## 🔗 Related Links

- [Main Project Repository](https://github.com/your-org/Common_Chronicle)
- [API Documentation](../README.md)
- [Contributing Guidelines](../CONTRIBUTING.md)

## 🐛 Issues & Support

- [Report Issues](https://github.com/your-org/Common_Chronicle/issues)
- [Feature Requests](https://github.com/your-org/Common_Chronicle/issues)
- [Documentation](https://github.com/your-org/Common_Chronicle/wiki)

---

Built with ❤️ for historians, researchers, and anyone curious about the past.
