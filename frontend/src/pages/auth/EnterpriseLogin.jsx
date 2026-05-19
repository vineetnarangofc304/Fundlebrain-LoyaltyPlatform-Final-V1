import LoginShell from "./LoginShell";

export default function EnterpriseLogin() {
  return (
    <LoginShell
      title="ENTERPRISE"
      subtitle="Enterprise Admin"
      portal="enterprise"
      redirectTo="/admin"
      dataTestPrefix="enterprise-login"
    />
  );
}
