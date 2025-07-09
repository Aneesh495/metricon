### Analytics Dashboard
- **Real-time Statistics**: Track total attempts, accuracy percentages, and performance metrics
- **Interactive Charts**: Visualize performance trends and accuracy patterns
- **Question Analysis**: Detailed breakdown of individual question performance
- **Difficulty Scoring**: Advanced algorithms to assess question difficulty levels

### Performance Insights
- **Smart Filtering**: Filter questions by correctness, accuracy, and attempt count
- **Benchmarking**: Compare your performance against aggregated data
- **Progress Tracking**: Monitor improvement over time with detailed analytics
- **Export Capabilities**: Download your data for external analysis

## Installation

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

## Running the Application

### Dev Mode
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
