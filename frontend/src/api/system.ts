/**
 * 系统管理 API（Phase 7 v0.7.2）。
 * 用 client.ts 的 axios（自动 Bearer + 401 refresh）。
 */
import { api } from "./client";
import type {
  PermissionOut,
  RoleCreate,
  RoleDetailOut,
  RoleOut,
  RoleUpdate,
  UserCreate,
  UserListItem,
  UserUpdate,
} from "@/types";

// ── Users ─────────────────────────────────────────────────

export const listUsers = () =>
  api.get<UserListItem[]>("/system/users").then((r) => r.data);

export const createUser = (payload: UserCreate) =>
  api.post<UserListItem>("/system/users", payload).then((r) => r.data);

export const updateUser = (id: number, payload: UserUpdate) =>
  api.put<UserListItem>(`/system/users/${id}`, payload).then((r) => r.data);

export const deleteUser = (id: number) =>
  api.delete(`/system/users/${id}`);

export const setUserRoles = (id: number, role_codes: string[]) =>
  api
    .put<UserListItem>(`/system/users/${id}/roles`, { role_codes })
    .then((r) => r.data);

export const resetUserPassword = (id: number, new_password: string) =>
  api.put(`/system/users/${id}/password`, { new_password });

// ── Roles ─────────────────────────────────────────────────

export const listRoles = () =>
  api.get<RoleOut[]>("/system/roles").then((r) => r.data);

export const getRole = (id: number) =>
  api.get<RoleDetailOut>(`/system/roles/${id}`).then((r) => r.data);

export const createRole = (payload: RoleCreate) =>
  api.post<RoleOut>("/system/roles", payload).then((r) => r.data);

export const updateRole = (id: number, payload: RoleUpdate) =>
  api.put<RoleOut>(`/system/roles/${id}`, payload).then((r) => r.data);

export const deleteRole = (id: number) => api.delete(`/system/roles/${id}`);

export const setRolePermissions = (id: number, permission_codes: string[]) =>
  api
    .put<RoleDetailOut>(`/system/roles/${id}/permissions`, { permission_codes })
    .then((r) => r.data);

// ── Permissions ───────────────────────────────────────────

export const listPermissions = () =>
  api.get<PermissionOut[]>("/system/permissions").then((r) => r.data);
