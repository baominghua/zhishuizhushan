import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";

export function useCapabilities() {
  return useQuery({
    queryKey: ["v2-capabilities"],
    queryFn: api.capabilities,
    staleTime: 60_000,
  });
}

export function hasPermission(
  permissions: string[] | undefined,
  roles: string[] | undefined,
  permission: string,
) {
  if (roles?.some((role) => role.toLowerCase() === "admin")) return true;
  if (!permissions) return false;
  if (permissions.includes("*") || permissions.includes(permission)) return true;
  const domain = permission.slice(0, permission.lastIndexOf("."));
  return permissions.includes(`${domain}.manage`);
}
