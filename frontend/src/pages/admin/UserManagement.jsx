import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, StatusPill } from "./_shared";
import { toast } from "sonner";
import { fmtDate } from "@/lib/format";
import { Plus, UserPlus, KeyRound, Power } from "lucide-react";
import { useAuth } from "@/lib/auth";

const ROLES = [
  "super_admin","brand_admin","crm_manager","marketing_manager","regional_manager",
  "store_manager","store_staff","support_agent","analytics_viewer","readonly_executive",
];

export default function UserManagement() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({ email: "", name: "", password: "", role: "store_manager", phone: "", region: "" });
  const [pwModal, setPwModal] = useState(null);
  const [newPw, setNewPw] = useState("");

  const load = async () => {
    const r = await api.get("/users");
    setUsers(r.data);
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    try {
      await api.post("/users", form);
      toast.success(`User ${form.email} created`);
      setShow(false);
      setForm({ email: "", name: "", password: "", role: "store_manager", phone: "", region: "" });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const toggleActive = async (u) => {
    try {
      await api.patch(`/users/${u.id}`, { is_active: !u.is_active });
      toast.success(`User ${u.is_active ? "deactivated" : "activated"}`);
      load();
    } catch (e) {
      toast.error("Failed");
    }
  };

  const resetPw = async () => {
    try {
      await api.post(`/users/${pwModal}/reset-password`, null, { params: { new_password: newPw } });
      toast.success("Password reset");
      setPwModal(null); setNewPw("");
    } catch (e) { toast.error("Failed"); }
  };

  const availableRoles = me?.role === "super_admin" ? ROLES : ROLES.filter((r) => r !== "super_admin");

  return (
    <div data-testid="user-management-page">
      <PageHeader title="User Management" subtitle="ROLE-BASED ACCESS"
        actions={<button className="k-btn kazo-bg-burgundy" onClick={() => setShow(true)} data-testid="new-user-btn"><UserPlus className="w-4 h-4" /> New user</button>} />
      <div className="p-8">
        <div className="bg-white border border-black/10 overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Phone</th><th>Last login</th><th>Created</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} data-testid={`user-row-${u.id}`}>
                  <td className="font-medium">{u.name}</td>
                  <td className="font-mono text-xs">{u.email}</td>
                  <td><span className="pill pill-neutral">{u.role.replace(/_/g, " ")}</span></td>
                  <td className="text-xs">{u.phone || "—"}</td>
                  <td className="text-xs">{u.last_login_at ? fmtDate(u.last_login_at) : "—"}</td>
                  <td className="text-xs">{fmtDate(u.created_at)}</td>
                  <td><StatusPill status={u.is_active ? "active" : "inactive"} /></td>
                  <td>
                    <div className="flex gap-1">
                      <button className="k-btn k-btn-ghost k-btn-sm" title="Reset password" onClick={() => setPwModal(u.id)} data-testid={`reset-${u.id}`}><KeyRound className="w-3.5 h-3.5" /></button>
                      <button className="k-btn k-btn-ghost k-btn-sm" title={u.is_active ? "Deactivate" : "Activate"} onClick={() => toggleActive(u)} data-testid={`toggle-${u.id}`}><Power className="w-3.5 h-3.5" /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white p-6 w-full max-w-lg" onClick={(e) => e.stopPropagation()} data-testid="new-user-modal">
            <h3 className="font-display text-2xl mb-4">Add User</h3>
            <div className="space-y-3">
              <input className="k-input" placeholder="Full name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="new-user-name" />
              <input className="k-input" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="new-user-email" />
              <input className="k-input" placeholder="Password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="new-user-password" />
              <input className="k-input" placeholder="Phone (optional)" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              <select className="k-input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} data-testid="new-user-role">
                {availableRoles.map((r) => <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}
              </select>
              <input className="k-input" placeholder="Region (optional)" value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} />
              <div className="flex justify-end gap-2 mt-2">
                <button className="k-btn k-btn-ghost" onClick={() => setShow(false)}>Cancel</button>
                <button className="k-btn kazo-bg-burgundy" onClick={create} data-testid="new-user-submit">Create user</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {pwModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setPwModal(null)}>
          <div className="bg-white p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-display text-2xl mb-4">Reset Password</h3>
            <input className="k-input" type="password" placeholder="New password (min 6 chars)" value={newPw} onChange={(e) => setNewPw(e.target.value)} data-testid="reset-pw-input" />
            <div className="flex justify-end gap-2 mt-4">
              <button className="k-btn k-btn-ghost" onClick={() => setPwModal(null)}>Cancel</button>
              <button className="k-btn kazo-bg-burgundy" onClick={resetPw} data-testid="reset-pw-confirm">Reset</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
