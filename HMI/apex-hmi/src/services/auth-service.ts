import api from './api';

export interface ModulePermission {
    canView: boolean;
    canOperate: boolean;
    canGenerate: boolean;
    canConfigure: boolean;
}

export interface UserPermissions {
    hmi?: ModulePermission;
    reports?: ModulePermission;
    analytics?: ModulePermission;
    alarms?: ModulePermission;
    admin?: ModulePermission;
    [key: string]: ModulePermission | undefined;
}

export interface User {
    id: string;
    username: string;
    role?: string;
    isAdmin?: boolean;
    mfaEnabled?: boolean;
    permissions?: UserPermissions;
    [key: string]: any;
}

export interface LoginResponse {
    success?: boolean;
    mfaRequired?: boolean;
    mustChangePassword?: boolean;
    tempToken?: string;
    setupToken?: string;
    token?: string;
    sessionToken?: string;
    sessionId?: number;
    user?: User;
}

export interface SecurityQuestion {
    question: string;
    answer: string;
}

export const authService = {
    async login(username: string, password: string): Promise<LoginResponse> {
        const response = await api.post('/auth/login', { username, password });
        return response.data;
    },

    async register(username: string, password: string, securityQuestions: SecurityQuestion[]): Promise<any> {
        const response = await api.post('/auth/register', { username, password, securityQuestions });
        return response.data;
    },

    async verifyMfa(tempToken: string, code?: string, questionIndex?: number, answer?: string): Promise<LoginResponse> {
        const payload: any = { tempToken };
        if (code) {
            payload.code = code;
        } else if (questionIndex !== undefined && answer) {
            payload.questionIndex = questionIndex;
            payload.answer = answer;
        }
        const response = await api.post('/auth/mfa/verify', payload);
        return response.data;
    },

    async validateToken(): Promise<{ valid: boolean; user?: User }> {
        const response = await api.get('/auth/validate');
        return response.data;
    },

    async setupMfa() {
        const response = await api.post('/auth/mfa/setup');
        return response.data;
    },

    async enableMfa(securityQuestions: SecurityQuestion[]) {
        const response = await api.post('/auth/mfa/enable', { securityQuestions });
        return response.data;
    },

    async checkResetUser(username: string): Promise<{ found: boolean; question?: { index: number; text: string } }> {
        const response = await api.post('/auth/reset-password/check', { username });
        return response.data;
    },

    async resetPassword(payload: { username: string; method: string; answer: string; newPassword: string; questionIndex?: number }) {
        const response = await api.post('/auth/reset-password', payload);
        return response.data;
    },

    async completeSetup(setupToken: string, newPassword: string, securityQuestions: SecurityQuestion[]): Promise<any> {
        const response = await api.post('/auth/complete-setup', { newPassword, securityQuestions }, {
            headers: { Authorization: `Bearer ${setupToken}` }
        });
        return response.data;
    }
};
