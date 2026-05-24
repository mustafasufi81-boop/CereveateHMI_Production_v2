import axios, { InternalAxiosRequestConfig, AxiosResponse, AxiosError } from 'axios';

// Get API URL from env or default to relative path
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Auth token and session token management (middleware)
let authInterceptorId: number | null = null;
let sessionInterceptorId: number | null = null;

export const setAuthToken = (token: string) => {
    // Remove existing interceptor if any
    if (authInterceptorId !== null) {
        api.interceptors.request.eject(authInterceptorId);
    }
    // Add new interceptor that injects the token
    authInterceptorId = api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
        config.headers.Authorization = `Bearer ${token}`;
        return config;
    });
};

export const setSessionToken = (sessionToken: string) => {
    // Remove existing interceptor if any
    if (sessionInterceptorId !== null) {
        api.interceptors.request.eject(sessionInterceptorId);
    }
    // Add new interceptor that injects the session token
    sessionInterceptorId = api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
        config.headers['X-Session-Token'] = sessionToken;
        return config;
    });
};

export const clearAuthToken = () => {
    if (authInterceptorId !== null) {
        api.interceptors.request.eject(authInterceptorId);
        authInterceptorId = null;
    }
};

export const clearSessionToken = () => {
    if (sessionInterceptorId !== null) {
        api.interceptors.request.eject(sessionInterceptorId);
        sessionInterceptorId = null;
    }
};

// Logout callback for session expiration handling
let logoutCallback: (() => void) | null = null;

export const registerLogoutCallback = (callback: () => void) => {
    logoutCallback = callback;
};

export const unregisterLogoutCallback = () => {
    logoutCallback = null;
};

// Response interceptor for handling 401 errors and session expiration
api.interceptors.response.use(
    (response: AxiosResponse) => response,
    (error: AxiosError) => {
        if (error.response?.status === 401) {
            const data = error.response?.data as any;

            // Session superseded — logged in from another device
            if (data?.code === 'SESSION_SUPERSEDED') {
                localStorage.removeItem('session_token');
                localStorage.removeItem('session_id');
                localStorage.removeItem('auth_token');
                localStorage.removeItem('auth_user');
                if (logoutCallback) logoutCallback();
                window.location.href = '/login?reason=superseded';
                return Promise.reject(error);
            }

            // Check if this is a session expiration (admin terminated or timeout)
            if (data?.sessionExpired) {
                console.warn('Session expired or terminated by admin');
                
                // Clear storage
                localStorage.removeItem('session_token');
                localStorage.removeItem('session_id');
                localStorage.removeItem('auth_token');
                
                // Trigger logout callback if registered
                if (logoutCallback) {
                    logoutCallback();
                }
            } else {
                // Regular 401 (invalid credentials, etc.)
                localStorage.removeItem('auth_token');
            }
        }
        return Promise.reject(error);
    }
);

export default api;
