import LoginShell from "./LoginShell";

export default function CRMLogin() {
  return (
    <LoginShell
      title="CRM"
      subtitle="CRM & Support"
      portal="crm"
      allowedRoles={["crm_manager", "support_agent", "super_admin", "brand_admin"]}
      redirectTo="/admin"
      dataTestPrefix="crm-login"
    />
  );
}
