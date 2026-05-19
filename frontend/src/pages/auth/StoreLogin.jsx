import LoginShell from "./LoginShell";

export default function StoreLogin() {
  return (
    <LoginShell
      title="STORE"
      subtitle="Store Operations"
      portal="store"
      allowedRoles={["store_manager", "store_staff", "super_admin", "brand_admin"]}
      redirectTo="/store"
      dataTestPrefix="store-login"
    />
  );
}
