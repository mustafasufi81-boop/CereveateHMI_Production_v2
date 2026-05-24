import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api, { setAuthToken, clearAuthToken, setSessionToken as setAPISessionToken, clearSessionToken as clearAPISessionToken, registerLogoutCallback, unregisterLogoutCallback } from '../services/api';
import { authService, User, SecurityQuestion } from '../services/auth-service';


interface AuthContextType {
    user: User | null;
    token: string | null;
    sessionToken: string | null;
    sessionId: number | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    mfaPending: boolean;
    tempToken: string | null;
    mfaSetupData: any;
    showMfaSetup: boolean;
    setupToken: string | null;
    login: (username: string, password: string) => Promise<{ success?: boolean; mfaRequired?: boolean; mustChangePassword?: boolean }>;
    verifyMfa: (code?: string, questionIndex?: number, answer?: string) => Promise<{ success: boolean }>;
    cancelMfa: () => void;
    register: (username: string, password: string, securityQuestions: SecurityQuestion[]) => Promise<{ success: boolean;[key: string]: any }>;
    logout: () => void;
    setupMfa: () => Promise<any>;
    enableMfa: (securityQuestions?: SecurityQuestion[]) => Promise<{ success: boolean; message: string }>;
    closeMfaSetup: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [user, setUser] = useState<User | null>(() => {
        const stored = localStorage.getItem('auth_user');
        if (!stored) return null;
        try {
            return JSON.parse(stored) as User;
        } catch {
            return null;
        }
    });
    const [token, setToken] = useState<string | null>(() => localStorage.getItem('auth_token'));
    const [sessionToken, setSessionToken] = useState<string | null>(() => localStorage.getItem('session_token'));
    const [sessionId, setSessionId] = useState<number | null>(() => {
        const stored = localStorage.getItem('session_id');
        return stored ? parseInt(stored, 10) : null;
    });
    const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
    const [isLoading, setIsLoading] = useState<boolean>(true);

    // MFA States
    const [mfaPending, setMfaPending] = useState<boolean>(false);
    const [tempToken, setTempToken] = useState<string | null>(null);
    const [mfaSetupData, setMfaSetupData] = useState<any>(null);
    const [showMfaSetup, setShowMfaSetup] = useState<boolean>(false);
    // Force password setup state (admin reset)
    const [setupToken, setSetupToken] = useState<string | null>(null);

    // Session heartbeat - check session validity every 30 seconds
    // Uses api service so 401 responses trigger automatic logout via interceptor
    useEffect(() => {
        if (!sessionToken) return;

        const heartbeatInterval = setInterval(async () => {
            try {
                // POST to update activity - will trigger 401 if session terminated
                await api.post('/session/activity');
            } catch (error: any) {
                // 401 with sessionExpired will be caught by api interceptor
                // Other errors logged here
                if (error?.response?.status !== 401) {
                    console.error('Session heartbeat failed:', error);
                }
            }
        }, 30 * 1000); // 30 seconds for faster session termination detection

        return () => clearInterval(heartbeatInterval);
    }, [sessionToken]);

    // Register logout callback for session expiration handling
    useEffect(() => {
        const handleSessionExpired = () => {
            // Force logout without calling backend (session already expired/terminated)
            localStorage.removeItem('auth_token');
            localStorage.removeItem('auth_user');
            localStorage.removeItem('session_token');
            localStorage.removeItem('session_id');
            clearAuthToken();
            clearAPISessionToken();
            setToken(null);
            setSessionToken(null);
            setSessionId(null);
            setUser(null);
            setIsAuthenticated(false);
            setMfaPending(false);
            setTempToken(null);
            setMfaSetupData(null);
            setShowMfaSetup(false);
            
            // Redirect to login with message
            window.location.href = '/login?session_expired=true';
        };

        registerLogoutCallback(handleSessionExpired);

        return () => {
            unregisterLogoutCallback();
        };
    }, []);

    useEffect(() => {
        const initAuth = async () => {
            const storedToken = localStorage.getItem('auth_token');
            const storedSessionToken = localStorage.getItem('session_token');
            
            if (storedToken) {
                setAuthToken(storedToken);
                
                if (storedSessionToken) {
                    setAPISessionToken(storedSessionToken);
                }
                
                try {
                    const data = await authService.validateToken();
                    if (data && data.valid && data.user) {
                        setUser(data.user);
                        localStorage.setItem('auth_user', JSON.stringify(data.user));
                        setToken(storedToken);
                        setIsAuthenticated(true);
                    } else {
                        logout();
                    }
                } catch (error) {
                    logout();
                }
            }
            setIsLoading(false);
        };
        initAuth();
    }, []);

    const login = useCallback(async (username: string, password: string) => {
        try {
            const data = await authService.login(username, password);

            if (data.mustChangePassword && data.setupToken) {
                setSetupToken(data.setupToken);
                return { mustChangePassword: true };
            } else if (data.mfaRequired && data.tempToken) {
                setMfaPending(true);
                setTempToken(data.tempToken);
                return { mfaRequired: true };
            } else if (data.token && data.user) {
                const authToken = data.token;
                localStorage.setItem('auth_token', authToken);
                setAuthToken(authToken);
                setToken(authToken);
                setUser(data.user);
                localStorage.setItem('auth_user', JSON.stringify(data.user));
                setIsAuthenticated(true);
                
                // Store session info
                if (data.sessionToken && data.sessionId) {
                    localStorage.setItem('session_token', data.sessionToken);
                    localStorage.setItem('session_id', data.sessionId.toString());
                    setAPISessionToken(data.sessionToken); // Set in axios headers
                    setSessionToken(data.sessionToken); // Set in local state
                    setSessionId(data.sessionId);
                }
                
                return { success: true };
            }
            return { success: false };
        } catch (error: any) {
            const message = error.response?.data?.message || 'Login failed';
            throw new Error(message);
        }
    }, []);

    const verifyMfa = useCallback(async (code?: string, questionIndex?: number, answer?: string) => {
        if (!tempToken) throw new Error('No pending MFA session');

        try {
            const data = await authService.verifyMfa(tempToken, code, questionIndex, answer);

            if (data.token && data.user) {
                const authToken = data.token;
                localStorage.setItem('auth_token', authToken);
                setAuthToken(authToken);
                setToken(authToken);
                setUser(data.user);
                localStorage.setItem('auth_user', JSON.stringify(data.user));
                setIsAuthenticated(true);
                setMfaPending(false);
                setTempToken(null);
                
                // Store session info
                if (data.sessionToken && data.sessionId) {
                    localStorage.setItem('session_token', data.sessionToken);
                    localStorage.setItem('session_id', data.sessionId.toString());
                    setAPISessionToken(data.sessionToken); // Set in axios headers
                    setSessionToken(data.sessionToken); // Set in local state  
                    setSessionId(data.sessionId);
                }
                
                return { success: true };
            }
            return { success: false };
        } catch (error: any) {
            const message = error.response?.data?.message || 'Invalid MFA code';
            throw new Error(message);
        }
    }, [tempToken]);

    const cancelMfa = useCallback(() => {
        setMfaPending(false);
        setTempToken(null);
    }, []);

    const register = useCallback(async (username: string, password: string, securityQuestions: SecurityQuestion[]) => {
        try {
            const data = await authService.register(username, password, securityQuestions);
            return { success: true, ...data };
        } catch (error: any) {
            const message = error.response?.data?.message || 'Registration failed';
            throw new Error(message);
        }
    }, []);

    const logout = useCallback(async () => {
        // Call logout API to end session
        if (sessionToken) {
            try {
                await fetch('/api/auth/logout', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`,
                        'X-Session-Token': sessionToken
                    },
                    body: JSON.stringify({ sessionToken })
                });
            } catch (error) {
                console.error('Logout API call failed:', error);
            }
        }
        
        // Clear local state
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_user');
        localStorage.removeItem('session_token');
        localStorage.removeItem('session_id');
        clearAuthToken();
        clearAPISessionToken();
        setToken(null);
        setSessionToken(null);
        setSessionId(null);
        setUser(null);
        setIsAuthenticated(false);
        setMfaPending(false);
        setTempToken(null);
        setMfaSetupData(null);
        setShowMfaSetup(false);
    }, [sessionToken, token]);

    const setupMfa = useCallback(async () => {
        try {
            const data = await authService.setupMfa();
            setMfaSetupData(data);
            setShowMfaSetup(true);
            return data;
        } catch (error: any) {
            const message = error.response?.data?.message || 'Failed to setup MFA';
            throw new Error(message);
        }
    }, []);

    const enableMfa = useCallback(async (securityQuestions: SecurityQuestion[] = []) => {
        try {
            const data = await authService.enableMfa(securityQuestions);
            setShowMfaSetup(false);
            setMfaSetupData(null);
            setUser(prev => prev ? { ...prev, mfaEnabled: true } : prev);
            return { success: true, message: data.message };
        } catch (error: any) {
            const message = error.response?.data?.message || 'Failed to enable MFA';
            throw new Error(message);
        }
    }, []);

    const closeMfaSetup = useCallback(() => {
        setShowMfaSetup(false);
        setMfaSetupData(null);
    }, []);

    const value = {
        user,
        token,
        sessionToken,
        sessionId,
        tempToken,
        setupToken,
        isAuthenticated,
        isLoading,
        mfaPending,
        mfaSetupData,
        showMfaSetup,
        login,
        verifyMfa,
        cancelMfa,
        register,
        logout,
        setupMfa,
        enableMfa,
        closeMfaSetup
    };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
};
