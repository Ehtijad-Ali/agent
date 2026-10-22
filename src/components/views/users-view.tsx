"use client";

import * as React from "react";
import { Loader2, ShieldCheck, UserPlus } from "lucide-react";

import {
  ApiError,
  type CurrentUser,
  type PlatformUser,
  type RoleInfo,
  createUser,
  listRoles,
  listUsers,
  me,
  updateUser,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

/**
 * User management (spec §38) — administrators only.
 *
 * The server enforces this too; the screen simply refuses to render controls a
 * non-admin cannot use, so an operator sees an explanation rather than a wall
 * of buttons that all return 403.
 */
export function UsersView() {
  const [users, setUsers] = React.useState<PlatformUser[]>([]);
  const [roles, setRoles] = React.useState<RoleInfo[]>([]);
  const [viewer, setViewer] = React.useState<CurrentUser | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [adding, setAdding] = React.useState(false);

  const refresh = React.useCallback(async () => {
    try {
      const who = await me();
      setViewer(who);
      const r = await listRoles();
      setRoles(r.roles);
      if (who?.role === "admin") {
        setUsers(await listUsers());
      }
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load users.");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading…
      </div>
    );
  }

  if (viewer?.role !== "admin") {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="max-w-sm space-y-2 text-center">
          <ShieldCheck className="mx-auto h-8 w-8 text-muted-foreground" />
          <h1 className="text-lg font-medium">Administrators only</h1>
          <p className="text-sm text-muted-foreground">
            Your account is an operator. You can review conversations and approve
            replies, but only an administrator can manage users.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-4 p-4 md:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Users</h1>
          <p className="text-sm text-muted-foreground">
            Who can sign in, and what they are allowed to do.
          </p>
        </div>
        <Button onClick={() => setAdding(true)} disabled={adding}>
          <UserPlus className="mr-2 h-4 w-4" /> Add user
        </Button>
      </header>

      <div className="grid gap-2 md:grid-cols-2">
        {roles.map((r) => (
          <div key={r.id} className="rounded-md border bg-muted/30 p-3">
            <p className="text-sm font-medium">{r.label}</p>
            <p className="text-xs text-muted-foreground">{r.description}</p>
          </div>
        ))}
      </div>

      {error ? (
        <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {adding ? (
        <AddUser
          roles={roles}
          onCancel={() => setAdding(false)}
          onDone={async () => {
            setAdding(false);
            await refresh();
          }}
        />
      ) : null}

      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50 text-left">
            <tr>
              <th className="p-3 font-medium">Name</th>
              <th className="p-3 font-medium">Email</th>
              <th className="p-3 font-medium">Role</th>
              <th className="p-3 font-medium">Last sign-in</th>
              <th className="p-3 font-medium">Active</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <UserRow
                key={u.id}
                user={u}
                isSelf={u.id === viewer.id}
                roles={roles}
                onChanged={refresh}
                onError={setError}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function UserRow({
  user,
  isSelf,
  roles,
  onChanged,
  onError,
}: {
  user: PlatformUser;
  isSelf: boolean;
  roles: RoleInfo[];
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = React.useState(false);

  async function patch(body: Parameters<typeof updateUser>[1]) {
    setBusy(true);
    try {
      await updateUser(user.id, body);
      onChanged();
    } catch (cause) {
      // The server refuses self-lockout and removing the last admin; surface
      // its message rather than silently reverting the control.
      onError(cause instanceof ApiError ? cause.message : "Could not update the user.");
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr className="border-t">
      <td className="p-3">
        {user.name}
        {isSelf ? <span className="ml-2 text-xs text-muted-foreground">(you)</span> : null}
      </td>
      <td className="p-3 text-muted-foreground">{user.email}</td>
      <td className="p-3">
        <select
          value={user.role}
          disabled={busy || isSelf}
          onChange={(e) => patch({ role: e.target.value })}
          className="h-8 rounded-md border bg-background px-2 text-sm disabled:opacity-60"
        >
          {roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.label}
            </option>
          ))}
        </select>
      </td>
      <td className="p-3 text-muted-foreground">
        {user.lastLoginAt ? new Date(user.lastLoginAt).toLocaleString() : "Never"}
      </td>
      <td className="p-3">
        <Switch
          checked={user.isActive}
          disabled={busy || isSelf}
          onCheckedChange={(isActive) => patch({ isActive })}
          aria-label={`${user.isActive ? "Deactivate" : "Activate"} ${user.email}`}
        />
      </td>
    </tr>
  );
}

function AddUser({
  roles,
  onCancel,
  onDone,
}: {
  roles: RoleInfo[];
  onCancel: () => void;
  onDone: () => void;
}) {
  const [email, setEmail] = React.useState("");
  const [name, setName] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [role, setRole] = React.useState("operator");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createUser({ email, name, password, role });
      onDone();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not create the user.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded-lg border bg-card p-4">
      <h2 className="font-medium">Add a user</h2>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="u-email">Email</Label>
          <Input
            id="u-email"
            type="email"
            required
            autoComplete="off"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={busy}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="u-name">Name</Label>
          <Input
            id="u-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="u-password">Password</Label>
          <Input
            id="u-password"
            type="password"
            required
            minLength={10}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
          />
          <p className="text-xs text-muted-foreground">
            At least 10 characters. Share it with them securely, and ask them to
            change it.
          </p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="u-role">Role</Label>
          <select
            id="u-role"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            disabled={busy}
            className="h-9 w-full rounded-md border bg-background px-3 text-sm"
          >
            {roles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
          <p className="text-xs text-muted-foreground">
            {roles.find((r) => r.id === role)?.description}
          </p>
        </div>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <div className="flex gap-2">
        <Button type="submit" disabled={busy}>
          {busy ? "Adding…" : "Add user"}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
