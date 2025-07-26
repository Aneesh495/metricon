# Boilerexams Frontend Application Project

A modern, interactive quiz analytics dashboard built with React, TypeScript, and Tailwind CSS. This application provides comprehensive insights into quiz performance, helping users track their progress, analyze question difficulty, and benchmark their results against others.

## 🚀 Features

### 📊 Analytics Dashboard
- **Real-time Statistics**: Track total attempts, accuracy percentages, and performance metrics
- **Interactive Charts**: Visualize performance trends and accuracy patterns
- **Question Analysis**: Detailed breakdown of individual question performance
- **Difficulty Scoring**: Advanced algorithms to assess question difficulty levels

### 🎯 Performance Insights
- **Smart Filtering**: Filter questions by correctness, accuracy, and attempt count
- **Benchmarking**: Compare your performance against aggregated data
- **Progress Tracking**: Monitor improvement over time with detailed analytics
- **Export Capabilities**: Download your data for external analysis

### 🎨 Modern UI/UX
- **Dark/Light Theme**: Seamless theme switching with system preference detection
- **Responsive Design**: Optimized for desktop, tablet, and mobile devices
- **Smooth Animations**: Enhanced user experience with Framer Motion
- **Accessibility**: Built with accessibility best practices

### 🔧 Technical Features
- **TypeScript**: Full type safety and better development experience
- **React Query**: Efficient data fetching and caching
- **Tailwind CSS**: Utility-first styling with custom design system
- **Vite**: Fast development and build tooling
- **Express Backend**: RESTful API with session management

## 🛠️ Tech Stack

### Frontend
- **React 18** - Modern React with hooks and concurrent features
- **TypeScript** - Type-safe development
- **Tailwind CSS** - Utility-first CSS framework
- **Radix UI** - Accessible component primitives
- **Framer Motion** - Smooth animations
- **React Query** - Data fetching and state management
- **Recharts** - Beautiful data visualizations
- **Lucide React** - Beautiful icons

### Backend
- **Express.js** - Fast, unopinionated web framework
- **WebSocket** - Real-time communication
- **Passport.js** - Authentication middleware

### Development Tools
- **Vite** - Next-generation frontend tooling
- **ESBuild** - Extremely fast JavaScript bundler

## 📦 Installation

### Prerequisites
- **Node.js** (v18 or higher)
- **npm** or **yarn** package manager

### Quick Start

1. **Clone the repository**
   ```bash
   git clone github.com/Aneesh495/LocalStorageStats
   cd LocalStorageStats
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

3. **Start the development server**
   ```bash
   npm run dev
   ```

4. **Open your browser**
   Navigate to `http://localhost:5001` to view the application.

## 🚀 Running the Application

### Development Mode
```bash
npm run dev
```
This starts both the frontend and backend servers in development mode with hot reloading.

### Production Build
```bash
# Build the application
npm run build

# Start the production server
npm start
```

### Available Scripts
- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm start` - Start production server
- `npm run check` - Type checking

## 📁 Project Structure

```
LocalStorageStats/
├── client/                 # Frontend React application
│   ├── src/
│   │   ├── components/    # Reusable UI components
│   │   ├── hooks/        # Custom React hooks
│   │   ├── pages/        # Page components
│   │   ├── types/        # TypeScript type definitions
│   │   ├── utils/        # Utility functions
│   │   └── lib/          # Library configurations
│   └── index.html        # HTML template
├── server/               # Backend Express application
│   ├── index.ts         # Server entry point
│   ├── routes.ts        # API route definitions
│   ├── storage.ts       # Database operations
│   └── vite.ts          # Vite configuration
├── shared/              # Shared code between frontend/backend
│   └── schema.ts        # Database schema definitions
└── package.json         # Project dependencies and scripts
```

## 🎯 Key Components

### Dashboard Features
- **Stats Overview**: High-level performance metrics
- **Performance Chart**: Visual representation of attempt history
- **Accuracy Chart**: Question-by-question accuracy analysis
- **Filters Panel**: Advanced filtering and sorting options
- **Questions List**: Detailed breakdown of individual questions
- **Difficulty Scoring**: AI-powered question difficulty assessment
- **Performance Insights**: Actionable recommendations
- **Benchmarking**: Comparative performance analysis

### Data Processing
The application processes quiz data from localStorage, providing:
- Real-time analytics
- Performance tracking
- Question difficulty analysis
- Export capabilities

## 🔧 Configuration

### Environment Variables
- `NODE_ENV`: Environment mode (development/production)
- `PORT`: Server port (default: 5001)
- `SESSION_SECRET`: Session encryption secret

## 🚀 Deployment

### Production Build
1. Set environment variables for production
2. Run `npm run build`
3. Start the server with `npm start`

### Docker Deployment (Optional)
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build
EXPOSE 5001
CMD ["npm", "start"]
```

## 🆘 Support

If you encounter any issues or have questions:
1. Check the existing issues in the repository
2. Create a new issue with detailed information
3. Include your environment details and error messages

## 🎉 Acknowledgments

- Built with modern web technologies
- Designed for optimal user experience
- Focused on performance and accessibility
- Comprehensive analytics and insights

## 🤖 AI Usage

This project utilizes AI assistance for:
- **README Generation**: This comprehensive documentation was created with AI assistance to ensure clarity and completeness
- **Minimal Debugging**: AI tools are occasionally used for basic debugging and code analysis

The core application functionality and architecture were developed through traditional software engineering practices.

---

**Happy coding! 🚀** 
