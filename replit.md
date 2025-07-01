# replit.md

## Overview

This is a comprehensive quiz analytics dashboard built with React, Express.js, and TypeScript. The application visualizes quiz submission data and performance metrics with an advanced, visually stunning interface. It features dark/light mode theming, interactive charts, AI-powered insights, difficulty analysis, data export capabilities, and benchmarking features. The UI is built with shadcn/ui components, Tailwind CSS, and enhanced with custom gradient backgrounds and smooth animations.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Framework**: React with TypeScript
- **Build Tool**: Vite for fast development and optimized builds
- **Styling**: Tailwind CSS with shadcn/ui component library
- **State Management**: TanStack Query for server state management
- **Routing**: Wouter for client-side routing
- **UI Components**: Radix UI primitives with custom styling

### Backend Architecture
- **Framework**: Express.js with TypeScript
- **Database**: PostgreSQL with Drizzle ORM
- **Database Provider**: Neon Database (serverless PostgreSQL)
- **Storage**: Custom storage interface with in-memory implementation

## Key Components

### Frontend Components
- **Dashboard**: Tabbed interface with Overview, Insights, Difficulty, and Benchmarks sections
- **Theme System**: Complete dark/light mode toggle with system preference detection
- **Charts**: Enhanced data visualization (AccuracyChart, PerformanceChart) with dark mode support
- **Filters**: Interactive filtering and sorting controls with improved UX
- **Stats Overview**: Animated metric cards with hover effects and color-coded indicators
- **Questions List**: Scrollable list with attempt timeline visualization
- **Difficulty Scoring**: AI-powered analysis categorizing questions by difficulty level
- **Performance Insights**: Intelligent feedback and recommendations based on user performance
- **Benchmarking**: User level comparison with achievement system
- **Export Functionality**: CSV and HTML report generation with comprehensive formatting

### Backend Components
- **Storage Interface**: Abstract storage layer with CRUD operations
- **Memory Storage**: In-memory implementation for development
- **Express Routes**: API endpoints (currently minimal setup)
- **Vite Integration**: Development server with HMR support

### Database Schema
- **Users Table**: Basic user authentication structure
  - id (serial, primary key)
  - username (text, unique)
  - password (text)

## Data Flow

1. **Quiz Data Source**: Currently reads from local storage containing quiz submission data
2. **Data Processing**: Client-side processing of quiz attempts and statistics
3. **State Management**: TanStack Query manages data fetching and caching
4. **Visualization**: Recharts components render performance metrics
5. **User Interaction**: Filters and sorting controls update displayed data

## External Dependencies

### Core Dependencies
- **@neondatabase/serverless**: Serverless PostgreSQL connection
- **drizzle-orm**: Type-safe database ORM
- **@tanstack/react-query**: Server state management
- **recharts**: Data visualization library
- **wouter**: Lightweight routing
- **date-fns**: Date manipulation utilities

### UI Dependencies
- **@radix-ui/***: Headless UI components
- **tailwindcss**: Utility-first CSS framework
- **class-variance-authority**: Type-safe variant styling
- **lucide-react**: Icon library

## Deployment Strategy

### Development
- Uses Vite development server with HMR
- Express server runs on Node.js with tsx for TypeScript execution
- Environment variables for database configuration

### Production Build
- Frontend: Vite builds optimized static assets
- Backend: esbuild bundles server code for Node.js
- Database: Drizzle manages schema migrations

### Key Scripts
- `dev`: Development server with hot reload
- `build`: Production build for both frontend and backend
- `start`: Production server
- `db:push`: Deploy database schema changes

## Recent Changes (January 2025)

✓ **Enhanced Dark/Light Mode**: Implemented comprehensive theme system with smooth transitions
✓ **Advanced Analytics**: Added difficulty scoring algorithm and performance insights
✓ **Export Capabilities**: CSV and HTML report generation with professional formatting
✓ **Benchmarking System**: User level progression with achievement tracking
✓ **UI/UX Improvements**: Gradient backgrounds, enhanced cards, custom scrollbars
✓ **Tabbed Navigation**: Organized features into Overview, Insights, Difficulty, and Benchmarks
✓ **Performance Optimization**: Enhanced chart rendering with dark mode compatibility

## Notes

- The application uses local storage for quiz data with sample data pre-loaded
- All components are optimized for both light and dark themes
- Export functionality generates professional reports with comprehensive analytics
- Difficulty scoring uses multiple factors: attempt count, accuracy, and improvement trends
- Benchmarking system simulates user progression levels from Beginner to Expert
- The application is fully responsive and optimized for Replit deployment