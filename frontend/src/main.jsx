import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { NewsCacheProvider } from './NewsCache'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <NewsCacheProvider>
        <App />
      </NewsCacheProvider>
    </BrowserRouter>
  </React.StrictMode>
)
