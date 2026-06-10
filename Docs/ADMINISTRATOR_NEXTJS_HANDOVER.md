# Acadexis Administration Frontend - Next.js Handover Guide

> **Handover Document:** Complete guide to integrating the Acadexis Administration API into your Next.js frontend admin dashboard.

---

## Table of Contents

1. [Overview](#overview)
2. [Environment Setup](#environment-setup)
3. [API Configuration](#api-configuration)
4. [Authentication Flow](#authentication-flow)
5. [API Utilities & Hooks](#api-utilities--hooks)
6. [Component Examples](#component-examples)
7. [State Management (Optional)](#state-management-optional)
8. [Error Handling & Validation](#error-handling--validation)
9. [Testing](#testing)
10. [Deployment Checklist](#deployment-checklist)

---

## Overview

### What You're Integrating

The **Acadexis Administration API** (`/api/admin/`) is a Django REST Framework API that provides complete admin functionality:

- ✅ User management (create, edit, deactivate, promote)
- ✅ University/Faculty/Department hierarchy
- ✅ Course management
- ✅ Student enrollments (single & bulk)
- ✅ Course materials upload & management
- ✅ Analytics & monitoring
- ✅ Search, filtering, pagination on all resources

### Architecture

```
Next.js Frontend (Your Admin Dashboard)
    ↓ (HTTPS + JWT Token)
    ↓
/api/admin/* (Django REST API)
    ↓
Authentication: JWT Bearer Token + is_staff=True
    ↓
CRUD Operations on Backend Models
```

### Authentication

- **Type:** JWT (JSON Web Tokens)
- **Flow:** Login → Get access/refresh tokens → Use access token in Authorization header
- **Required:** `is_staff=True` on user account
- **Token Expiry:** Access tokens expire after 60 minutes (configurable)
- **Refresh:** Use refresh token to get new access token without re-logging in

---

## Environment Setup

### 1. Install Dependencies

```bash
npm install axios zustand react-query
# or with yarn
yarn add axios zustand react-query
```

**Recommended Additional Packages:**

```bash
npm install date-fns clsx tailwind-merge react-toastify react-hook-form
```

### 2. Environment Variables

Create `.env.local` in your Next.js root:

```env
# Backend API
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_API_BASE_URL_PROD=https://api.acadexis.com

# Admin Dashboard
NEXT_PUBLIC_ADMIN_DASHBOARD_URL=http://localhost:3001
NEXT_PUBLIC_ADMIN_DASHBOARD_URL_PROD=https://admin.acadexis.com

# Feature Flags
NEXT_PUBLIC_ENABLE_AUDIT_LOGS=true
NEXT_PUBLIC_ENABLE_BULK_OPERATIONS=true
```

### 3. Create API Base Configuration

**`lib/api/config.ts`**

```typescript
const API_BASE_URL = 
  process.env.NODE_ENV === 'production'
    ? process.env.NEXT_PUBLIC_API_BASE_URL_PROD
    : process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

export const API_CONFIG = {
  BASE_URL: API_BASE_URL,
  TIMEOUT: 30000,
  RETRY_ATTEMPTS: 3,
  RETRY_DELAY: 1000,
};

export const API_ENDPOINTS = {
  AUTH: {
    LOGIN: '/api/auth/login/',
    LOGOUT: '/api/auth/logout/',
    REFRESH: '/api/auth/refresh/',
  },
  ADMIN: {
    USERS: '/api/admin/users/',
    UNIVERSITIES: '/api/admin/universities/',
    FACULTIES: '/api/admin/faculties/',
    DEPARTMENTS: '/api/admin/departments/',
    COURSES: '/api/admin/courses/',
    ENROLLMENTS: '/api/admin/enrollments/',
    MATERIALS: '/api/admin/materials/',
    RATINGS: '/api/admin/ratings/',
    STUDY_SESSIONS: '/api/admin/study-sessions/',
  },
};
```

---

## API Configuration

### Axios Instance with JWT Interceptors

**`lib/api/client.ts`**

```typescript
import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { API_CONFIG, API_ENDPOINTS } from './config';

let accessToken: string | null = null;

const createClient = (): AxiosInstance => {
  const client = axios.create({
    baseURL: API_CONFIG.BASE_URL,
    timeout: API_CONFIG.TIMEOUT,
    headers: {
      'Content-Type': 'application/json',
    },
  });

  // Request interceptor: Add JWT token to headers
  client.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      const token = accessToken || localStorage.getItem('access_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    },
    (error) => Promise.reject(error)
  );

  // Response interceptor: Handle 401 & token refresh
  client.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

      if (error.response?.status === 401 && !originalRequest._retry) {
        originalRequest._retry = true;

        try {
          const refreshToken = localStorage.getItem('refresh_token');
          if (!refreshToken) throw new Error('No refresh token available');

          const { data } = await axios.post(
            `${API_CONFIG.BASE_URL}${API_ENDPOINTS.AUTH.REFRESH}/`,
            { refresh: refreshToken }
          );

          accessToken = data.access;
          localStorage.setItem('access_token', data.access);

          originalRequest.headers.Authorization = `Bearer ${data.access}`;
          return client(originalRequest);
        } catch (refreshError) {
          // Refresh failed - redirect to login
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          window.location.href = '/admin/login';
          return Promise.reject(refreshError);
        }
      }

      return Promise.reject(error);
    }
  );

  return client;
};

export const apiClient = createClient();

// Utility to set token after login
export const setAuthToken = (token: string) => {
  accessToken = token;
  localStorage.setItem('access_token', token);
};

// Utility to clear token on logout
export const clearAuthToken = () => {
  accessToken = null;
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
};
```

---

## Authentication Flow

### Login Hook

**`hooks/useAuth.ts`**

```typescript
import { useState, useCallback } from 'react';
import { useRouter } from 'next/router';
import { apiClient, setAuthToken, clearAuthToken } from '@/lib/api/client';
import { API_ENDPOINTS } from '@/lib/api/config';

interface LoginCredentials {
  email: string;
  password: string;
}

interface AuthUser {
  id: string;
  email: string;
  role: string;
  is_staff: boolean;
  first_name: string;
  last_name: string;
}

export const useAuth = () => {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const login = useCallback(async (credentials: LoginCredentials) => {
    setLoading(true);
    setError(null);

    try {
      const { data } = await apiClient.post(API_ENDPOINTS.AUTH.LOGIN, credentials);

      // Store tokens
      localStorage.setItem('access_token', data.access);
      localStorage.setItem('refresh_token', data.refresh);
      setAuthToken(data.access);

      // Store user
      setUser(data.user);

      // Verify staff status
      if (!data.user.is_staff) {
        throw new Error('You do not have admin access.');
      }

      // Redirect to admin dashboard
      await router.push('/admin/dashboard');

      return { success: true };
    } catch (err: any) {
      const errorMsg =
        err.response?.data?.detail ||
        err.response?.data?.non_field_errors?.[0] ||
        'Login failed. Please check your credentials.';
      setError(errorMsg);
      return { success: false, error: errorMsg };
    } finally {
      setLoading(false);
    }
  }, [router]);

  const logout = useCallback(async () => {
    setLoading(true);

    try {
      await apiClient.post(API_ENDPOINTS.AUTH.LOGOUT);
    } catch (err) {
      // Logout endpoint might fail, but we still clear local auth
      console.error('Logout API error:', err);
    } finally {
      clearAuthToken();
      setUser(null);
      setLoading(false);
      await router.push('/admin/login');
    }
  }, [router]);

  const refreshUser = useCallback(async () => {
    try {
      const { data } = await apiClient.get(API_ENDPOINTS.ADMIN.USERS + 'me/');
      setUser(data);
    } catch (err) {
      console.error('Failed to refresh user:', err);
    }
  }, []);

  return { user, loading, error, login, logout, refreshUser };
};
```

### Protected Route Wrapper

**`components/ProtectedRoute.tsx`**

```typescript
import { ReactNode, useEffect, useState } from 'react';
import { useRouter } from 'next/router';

interface ProtectedRouteProps {
  children: ReactNode;
  requiredRole?: 'admin' | 'staff';
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  requiredRole = 'staff',
}) => {
  const router = useRouter();
  const [isAuthorized, setIsAuthorized] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem('access_token');
      const user = localStorage.getItem('admin_user');

      if (!token || !user) {
        await router.push('/admin/login');
        return;
      }

      const userData = JSON.parse(user);

      // Check role requirements
      if (requiredRole === 'admin' && !userData.is_superuser) {
        await router.push('/admin/unauthorized');
        return;
      }

      setIsAuthorized(true);
      setLoading(false);
    };

    checkAuth();
  }, [router, requiredRole]);

  if (loading) {
    return <div className="flex items-center justify-center min-h-screen">Loading...</div>;
  }

  return isAuthorized ? <>{children}</> : null;
};
```

---

## API Utilities & Hooks

### Generic API Hook

**`hooks/useAdminApi.ts`**

```typescript
import { useState, useCallback } from 'react';
import { apiClient } from '@/lib/api/client';

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ApiError {
  detail?: string;
  [key: string]: any;
}

export const useAdminApi = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const get = useCallback(
    async <T = any>(url: string, params: any = {}): Promise<T | null> => {
      setLoading(true);
      setError(null);

      try {
        const { data } = await apiClient.get<T>(url, { params });
        return data;
      } catch (err: any) {
        const errorData = err.response?.data || { detail: err.message };
        setError(errorData);
        console.error('API GET error:', errorData);
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const post = useCallback(
    async <T = any>(url: string, payload: any = {}): Promise<T | null> => {
      setLoading(true);
      setError(null);

      try {
        const { data } = await apiClient.post<T>(url, payload);
        return data;
      } catch (err: any) {
        const errorData = err.response?.data || { detail: err.message };
        setError(errorData);
        console.error('API POST error:', errorData);
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const patch = useCallback(
    async <T = any>(url: string, payload: any = {}): Promise<T | null> => {
      setLoading(true);
      setError(null);

      try {
        const { data } = await apiClient.patch<T>(url, payload);
        return data;
      } catch (err: any) {
        const errorData = err.response?.data || { detail: err.message };
        setError(errorData);
        console.error('API PATCH error:', errorData);
        return null;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const delete_ = useCallback(
    async (url: string): Promise<boolean> => {
      setLoading(true);
      setError(null);

      try {
        await apiClient.delete(url);
        return true;
      } catch (err: any) {
        const errorData = err.response?.data || { detail: err.message };
        setError(errorData);
        console.error('API DELETE error:', errorData);
        return false;
      } finally {
        setLoading(false);
      }
    },
    []
  );

  return { get, post, patch, delete_, loading, error };
};
```

### Specialized Hooks

**`hooks/useAdminUsers.ts`**

```typescript
import { useState, useCallback } from 'react';
import { API_ENDPOINTS } from '@/lib/api/config';
import { useAdminApi, PaginatedResponse } from './useAdminApi';

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: 'student' | 'lecturer' | 'admin';
  is_active: boolean;
  is_staff: boolean;
  university: string;
  university_name: string;
  date_joined: string;
}

export const useAdminUsers = () => {
  const { get, post, patch, delete_, loading, error } = useAdminApi();
  const [users, setUsers] = useState<User[]>([]);
  const [pagination, setPagination] = useState({ count: 0, next: null, previous: null });

  const fetchUsers = useCallback(
    async (filters: Record<string, any> = {}, page = 1) => {
      const params = { page, ...filters };
      const response = await get<PaginatedResponse<User>>(
        API_ENDPOINTS.ADMIN.USERS,
        params
      );

      if (response) {
        setUsers(response.results);
        setPagination({
          count: response.count,
          next: response.next,
          previous: response.previous,
        });
      }

      return response;
    },
    [get]
  );

  const createUser = useCallback(
    async (userData: Partial<User>) => {
      const result = await post(API_ENDPOINTS.ADMIN.USERS, userData);
      if (result) {
        setUsers((prev) => [...prev, result as User]);
      }
      return result;
    },
    [post]
  );

  const updateUser = useCallback(
    async (userId: string, updates: Partial<User>) => {
      const result = await patch(`${API_ENDPOINTS.ADMIN.USERS}${userId}/`, updates);
      if (result) {
        setUsers((prev) =>
          prev.map((u) => (u.id === userId ? { ...u, ...result } : u))
        );
      }
      return result;
    },
    [patch]
  );

  const deactivateUser = useCallback(
    async (userId: string) => {
      const result = await post(`${API_ENDPOINTS.ADMIN.USERS}${userId}/deactivate/`);
      if (result) {
        setUsers((prev) =>
          prev.map((u) => (u.id === userId ? { ...u, is_active: false } : u))
        );
      }
      return result;
    },
    [post]
  );

  const activateUser = useCallback(
    async (userId: string) => {
      const result = await post(`${API_ENDPOINTS.ADMIN.USERS}${userId}/activate/`);
      if (result) {
        setUsers((prev) =>
          prev.map((u) => (u.id === userId ? { ...u, is_active: true } : u))
        );
      }
      return result;
    },
    [post]
  );

  const promoteToStaff = useCallback(
    async (userId: string) => {
      const result = await post(`${API_ENDPOINTS.ADMIN.USERS}${userId}/promote_to_staff/`);
      if (result) {
        setUsers((prev) =>
          prev.map((u) => (u.id === userId ? { ...u, is_staff: true } : u))
        );
      }
      return result;
    },
    [post]
  );

  return {
    users,
    loading,
    error,
    pagination,
    fetchUsers,
    createUser,
    updateUser,
    deactivateUser,
    activateUser,
    promoteToStaff,
  };
};
```

**`hooks/useAdminCourses.ts`**

```typescript
import { useState, useCallback } from 'react';
import { API_ENDPOINTS } from '@/lib/api/config';
import { useAdminApi, PaginatedResponse } from './useAdminApi';

export interface Course {
  id: string;
  title: string;
  code: string;
  description: string;
  department: string;
  department_name: string;
  lecturer: string;
  lecturer_email: string;
  level: string;
  thumbnail: string | null;
  enrollment_count: number;
  material_count: number;
  created_at: string;
  updated_at: string;
}

export const useAdminCourses = () => {
  const { get, post, patch, delete_, loading, error } = useAdminApi();
  const [courses, setCourses] = useState<Course[]>([]);
  const [pagination, setPagination] = useState({ count: 0, next: null, previous: null });

  const fetchCourses = useCallback(
    async (filters: Record<string, any> = {}, page = 1) => {
      const params = { page, ...filters };
      const response = await get<PaginatedResponse<Course>>(
        API_ENDPOINTS.ADMIN.COURSES,
        params
      );

      if (response) {
        setCourses(response.results);
        setPagination({
          count: response.count,
          next: response.next,
          previous: response.previous,
        });
      }

      return response;
    },
    [get]
  );

  const createCourse = useCallback(
    async (courseData: Partial<Course>) => {
      const result = await post(API_ENDPOINTS.ADMIN.COURSES, courseData);
      if (result) {
        setCourses((prev) => [...prev, result as Course]);
      }
      return result;
    },
    [post]
  );

  const updateCourse = useCallback(
    async (courseId: string, updates: Partial<Course>) => {
      const result = await patch(`${API_ENDPOINTS.ADMIN.COURSES}${courseId}/`, updates);
      if (result) {
        setCourses((prev) =>
          prev.map((c) => (c.id === courseId ? { ...c, ...result } : c))
        );
      }
      return result;
    },
    [patch]
  );

  const deleteCourse = useCallback(
    async (courseId: string) => {
      const success = await delete_(`${API_ENDPOINTS.ADMIN.COURSES}${courseId}/`);
      if (success) {
        setCourses((prev) => prev.filter((c) => c.id !== courseId));
      }
      return success;
    },
    [delete_]
  );

  return {
    courses,
    loading,
    error,
    pagination,
    fetchCourses,
    createCourse,
    updateCourse,
    deleteCourse,
  };
};
```

**`hooks/useAdminEnrollments.ts`**

```typescript
import { useCallback } from 'react';
import { API_ENDPOINTS } from '@/lib/api/config';
import { useAdminApi } from './useAdminApi';

export interface BulkEnrollRequest {
  course_id: string;
  student_ids: string[];
}

export interface BulkEnrollResponse {
  detail: string;
  enrolled_count: number;
}

export const useAdminEnrollments = () => {
  const { post, loading, error } = useAdminApi();

  const bulkEnroll = useCallback(
    async (request: BulkEnrollRequest) => {
      const result = await post<BulkEnrollResponse>(
        `${API_ENDPOINTS.ADMIN.ENROLLMENTS}bulk_enroll/`,
        request
      );
      return result;
    },
    [post]
  );

  return {
    bulkEnroll,
    loading,
    error,
  };
};
```

---

## Component Examples

### Login Page

**`pages/admin/login.tsx`**

```typescript
import { useState } from 'react';
import { useRouter } from 'next/router';
import { useAuth } from '@/hooks/useAuth';

export default function AdminLogin() {
  const router = useRouter();
  const { login, loading, error } = useAuth();
  const [formData, setFormData] = useState({ email: '', password: '' });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const { success } = await login(formData);
    if (success) {
      await router.push('/admin/dashboard');
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-gray-100">
      <div className="w-full max-w-md bg-white rounded-lg shadow-md p-8">
        <h1 className="text-3xl font-bold text-center mb-6">Admin Login</h1>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700">Email</label>
            <input
              type="email"
              name="email"
              required
              value={formData.email}
              onChange={handleChange}
              className="w-full px-4 py-2 mt-1 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700">Password</label>
            <input
              type="password"
              name="password"
              required
              value={formData.password}
              onChange={handleChange}
              className="w-full px-4 py-2 mt-1 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-500 text-white py-2 rounded-lg hover:bg-blue-600 disabled:opacity-50"
          >
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </form>
      </div>
    </div>
  );
}
```

### Users Management Page

**`pages/admin/users/index.tsx`**

```typescript
import { useEffect, useState } from 'react';
import { useAdminUsers } from '@/hooks/useAdminUsers';
import { ProtectedRoute } from '@/components/ProtectedRoute';

export default function UsersPage() {
  const { users, loading, pagination, fetchUsers, deactivateUser } = useAdminUsers();
  const [filters, setFilters] = useState({ role: '', search: '' });
  const [currentPage, setCurrentPage] = useState(1);

  useEffect(() => {
    fetchUsers(filters, currentPage);
  }, [filters, currentPage, fetchUsers]);

  return (
    <ProtectedRoute requiredRole="staff">
      <div className="p-6">
        <h1 className="text-3xl font-bold mb-6">Users Management</h1>

        {/* Filters */}
        <div className="mb-6 flex gap-4">
          <input
            type="text"
            placeholder="Search by email or name..."
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            className="px-4 py-2 border border-gray-300 rounded-lg"
          />

          <select
            value={filters.role}
            onChange={(e) => setFilters({ ...filters, role: e.target.value })}
            className="px-4 py-2 border border-gray-300 rounded-lg"
          >
            <option value="">All Roles</option>
            <option value="student">Student</option>
            <option value="lecturer">Lecturer</option>
            <option value="admin">Admin</option>
          </select>
        </div>

        {/* Users Table */}
        {loading ? (
          <p>Loading...</p>
        ) : (
          <>
            <table className="w-full border-collapse border border-gray-300">
              <thead className="bg-gray-100">
                <tr>
                  <th className="border px-4 py-2 text-left">Email</th>
                  <th className="border px-4 py-2 text-left">Name</th>
                  <th className="border px-4 py-2 text-left">Role</th>
                  <th className="border px-4 py-2 text-left">Status</th>
                  <th className="border px-4 py-2 text-left">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td className="border px-4 py-2">{user.email}</td>
                    <td className="border px-4 py-2">
                      {user.first_name} {user.last_name}
                    </td>
                    <td className="border px-4 py-2 capitalize">{user.role}</td>
                    <td className="border px-4 py-2">
                      <span
                        className={`px-2 py-1 rounded text-white ${
                          user.is_active ? 'bg-green-500' : 'bg-red-500'
                        }`}
                      >
                        {user.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="border px-4 py-2">
                      {user.is_active ? (
                        <button
                          onClick={() => deactivateUser(user.id)}
                          className="text-red-500 hover:underline"
                        >
                          Deactivate
                        </button>
                      ) : (
                        <button
                          onClick={() => deactivateUser(user.id)}
                          className="text-green-500 hover:underline"
                        >
                          Activate
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            <div className="mt-6 flex gap-4">
              {pagination.previous && (
                <button
                  onClick={() => setCurrentPage(currentPage - 1)}
                  className="px-4 py-2 bg-blue-500 text-white rounded"
                >
                  Previous
                </button>
              )}
              <span className="px-4 py-2">
                Page {currentPage} of {Math.ceil(pagination.count / 20)}
              </span>
              {pagination.next && (
                <button
                  onClick={() => setCurrentPage(currentPage + 1)}
                  className="px-4 py-2 bg-blue-500 text-white rounded"
                >
                  Next
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </ProtectedRoute>
  );
}
```

### Courses Management Page

**`pages/admin/courses/index.tsx`**

```typescript
import { useEffect, useState } from 'react';
import { useAdminCourses } from '@/hooks/useAdminCourses';
import { ProtectedRoute } from '@/components/ProtectedRoute';

export default function CoursesPage() {
  const { courses, loading, fetchCourses, createCourse } = useAdminCourses();
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    title: '',
    code: '',
    description: '',
    department: '',
    lecturer: '',
    level: '',
  });

  useEffect(() => {
    fetchCourses();
  }, [fetchCourses]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await createCourse(formData);
    setFormData({ title: '', code: '', description: '', department: '', lecturer: '', level: '' });
    setShowForm(false);
  };

  return (
    <ProtectedRoute requiredRole="staff">
      <div className="p-6">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold">Courses Management</h1>
          <button
            onClick={() => setShowForm(!showForm)}
            className="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600"
          >
            {showForm ? 'Cancel' : 'Add Course'}
          </button>
        </div>

        {/* Create Course Form */}
        {showForm && (
          <form onSubmit={handleSubmit} className="mb-6 p-4 border border-gray-300 rounded-lg">
            <div className="grid grid-cols-2 gap-4">
              <input
                type="text"
                placeholder="Course Title"
                required
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                className="px-4 py-2 border border-gray-300 rounded"
              />
              <input
                type="text"
                placeholder="Course Code"
                required
                value={formData.code}
                onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                className="px-4 py-2 border border-gray-300 rounded"
              />
              <textarea
                placeholder="Description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="col-span-2 px-4 py-2 border border-gray-300 rounded"
              />
              <input
                type="text"
                placeholder="Department UUID"
                required
                value={formData.department}
                onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                className="px-4 py-2 border border-gray-300 rounded"
              />
              <input
                type="text"
                placeholder="Lecturer UUID"
                value={formData.lecturer}
                onChange={(e) => setFormData({ ...formData, lecturer: e.target.value })}
                className="px-4 py-2 border border-gray-300 rounded"
              />
            </div>
            <button
              type="submit"
              className="mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
            >
              Create Course
            </button>
          </form>
        )}

        {/* Courses List */}
        {loading ? (
          <p>Loading...</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {courses.map((course) => (
              <div key={course.id} className="p-4 border border-gray-300 rounded-lg shadow">
                <h3 className="text-lg font-bold">{course.title}</h3>
                <p className="text-sm text-gray-600">{course.code}</p>
                <p className="text-sm mt-2">{course.description}</p>
                <div className="mt-4 flex justify-between">
                  <span className="text-xs text-gray-500">
                    Enrollments: {course.enrollment_count}
                  </span>
                  <span className="text-xs text-gray-500">
                    Materials: {course.material_count}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </ProtectedRoute>
  );
}
```

### Bulk Enrollment Page

**`pages/admin/enrollments/bulk.tsx`**

```typescript
import { useState } from 'react';
import { useAdminEnrollments } from '@/hooks/useAdminEnrollments';
import { ProtectedRoute } from '@/components/ProtectedRoute';

export default function BulkEnrollPage() {
  const { bulkEnroll, loading, error } = useAdminEnrollments();
  const [courseId, setCourseId] = useState('');
  const [studentIds, setStudentIds] = useState('');
  const [success, setSuccess] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSuccess('');

    const ids = studentIds.split('\n').filter((id) => id.trim());
    const result = await bulkEnroll({
      course_id: courseId,
      student_ids: ids,
    });

    if (result) {
      setSuccess(`Successfully enrolled ${result.enrolled_count} students!`);
      setCourseId('');
      setStudentIds('');
    }
  };

  return (
    <ProtectedRoute requiredRole="staff">
      <div className="p-6">
        <h1 className="text-3xl font-bold mb-6">Bulk Enroll Students</h1>

        <form onSubmit={handleSubmit} className="max-w-md space-y-4">
          {error && (
            <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
              {JSON.stringify(error)}
            </div>
          )}

          {success && (
            <div className="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded">
              {success}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium">Course ID</label>
            <input
              type="text"
              required
              value={courseId}
              onChange={(e) => setCourseId(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded"
              placeholder="Paste course UUID"
            />
          </div>

          <div>
            <label className="block text-sm font-medium">Student IDs (one per line)</label>
            <textarea
              required
              value={studentIds}
              onChange={(e) => setStudentIds(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded h-40"
              placeholder="Paste student UUIDs, one per line"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
          >
            {loading ? 'Processing...' : 'Enroll Students'}
          </button>
        </form>
      </div>
    </ProtectedRoute>
  );
}
```

---

## State Management (Optional)

For larger apps, use **Zustand** store:

**`store/adminStore.ts`**

```typescript
import { create } from 'zustand';

interface User {
  id: string;
  email: string;
  role: string;
  is_staff: boolean;
}

interface AdminStore {
  user: User | null;
  token: string | null;
  setUser: (user: User) => void;
  setToken: (token: string) => void;
  logout: () => void;
}

export const useAdminStore = create<AdminStore>((set) => ({
  user: null,
  token: localStorage.getItem('access_token') || null,

  setUser: (user) => set({ user }),

  setToken: (token) => {
    localStorage.setItem('access_token', token);
    set({ token });
  },

  logout: () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    set({ user: null, token: null });
  },
}));
```

---

## Error Handling & Validation

### Global Error Boundary

**`components/ErrorBoundary.tsx`**

```typescript
import { ReactNode } from 'react';
import { toast } from 'react-toastify';

interface Props {
  children: ReactNode;
  onError?: (error: Error) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error) {
    this.props.onError?.(error);
    toast.error(error.message);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 bg-red-100 border border-red-400 text-red-700 rounded">
          <h2>Something went wrong</h2>
          <details className="mt-2">
            {this.state.error?.toString()}
          </details>
        </div>
      );
    }

    return this.props.children;
  }
}
```

### Toast Notifications

**`lib/notifications.ts`**

```typescript
import { toast } from 'react-toastify';

export const notify = {
  success: (message: string) => toast.success(message),
  error: (message: string) => toast.error(message),
  warning: (message: string) => toast.warning(message),
  info: (message: string) => toast.info(message),
};
```

---

## Testing

### Example Tests with Jest & React Testing Library

**`__tests__/useAdminUsers.test.ts`**

```typescript
import { renderHook, act } from '@testing-library/react';
import { useAdminUsers } from '@/hooks/useAdminUsers';
import * as apiClient from '@/lib/api/client';

jest.mock('@/lib/api/client');

describe('useAdminUsers', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should fetch users successfully', async () => {
    const mockUsers = [
      {
        id: '1',
        email: 'user@example.com',
        first_name: 'John',
        last_name: 'Doe',
        role: 'student',
        is_active: true,
        is_staff: false,
        university: 'univ-1',
        university_name: 'MIT',
        date_joined: '2024-01-01',
      },
    ];

    (apiClient.apiClient.get as jest.Mock).mockResolvedValueOnce({
      data: {
        count: 1,
        results: mockUsers,
        next: null,
        previous: null,
      },
    });

    const { result } = renderHook(() => useAdminUsers());

    await act(async () => {
      await result.current.fetchUsers();
    });

    expect(result.current.users).toEqual(mockUsers);
    expect(result.current.pagination.count).toBe(1);
  });
});
```

---

## Deployment Checklist

- [ ] Environment variables configured in `.env.local` and `.env.production`
- [ ] API base URL set correctly for production backend
- [ ] JWT token refresh logic tested
- [ ] Protected routes verified
- [ ] Error handling tested
- [ ] Pagination working on all list pages
- [ ] Search/filter functionality tested
- [ ] Bulk operations tested
- [ ] Staff-only routes protected
- [ ] CORS configured on backend
- [ ] HTTPS enforced
- [ ] Sensitive data not logged
- [ ] Rate limiting observed
- [ ] Performance tested (load time, API response times)

---

## Key API Endpoints Reference

```
Authentication:
POST   /api/auth/login/              → Get tokens
POST   /api/auth/refresh/            → Refresh access token

Admin Resources:
GET    /api/admin/users/             → List users
POST   /api/admin/users/             → Create user
GET    /api/admin/users/{id}/        → Get user
PATCH  /api/admin/users/{id}/        → Update user
POST   /api/admin/users/{id}/deactivate/    → Deactivate
POST   /api/admin/users/{id}/activate/      → Activate
POST   /api/admin/users/{id}/promote_to_staff/ → Promote

GET    /api/admin/courses/           → List courses
POST   /api/admin/courses/           → Create course
PATCH  /api/admin/courses/{id}/      → Update course

GET    /api/admin/enrollments/       → List enrollments
POST   /api/admin/enrollments/bulk_enroll/  → Bulk enroll

GET    /api/admin/materials/         → List materials
POST   /api/admin/materials/         → Upload material

GET    /api/admin/universities/      → List universities
GET    /api/admin/faculties/         → List faculties
GET    /api/admin/departments/       → List departments
```

---

## Support & Documentation

- **Backend Docs:** See `Docs/ADMINISTRATION_API.md` in the backend repo
- **Backend Setup:** See `Docs/SETUP_ADMIN_API.md`
- **OpenAPI Schema:** Available at `/api/docs/swagger/` (when backend running)

---

## Questions?

Refer to the backend documentation or reach out to the backend team for API clarifications.
