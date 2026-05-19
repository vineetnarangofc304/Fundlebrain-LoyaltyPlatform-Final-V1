import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "./_shared";
import { fmtDate } from "@/lib/format";

export default function StoresPage() {
  const [stores, setStores] = useState([]);
  useEffect(() => { api.get("/stores").then((r) => setStores(r.data)); }, []);
  return (
    <div data-testid="stores-page">
      <PageHeader title="Stores" subtitle="RETAIL FOOTPRINT" />
      <div className="p-8">
        <div className="bg-white border border-black/10 overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Code</th><th>Name</th><th>City</th><th>State</th><th>Region</th><th>Manager</th><th>Phone</th></tr></thead>
            <tbody>
              {stores.map((s) => (
                <tr key={s.id}>
                  <td className="font-mono text-xs">{s.code}</td>
                  <td className="font-medium">{s.name}</td>
                  <td>{s.city}</td>
                  <td>{s.state}</td>
                  <td><span className="pill pill-neutral">{s.region}</span></td>
                  <td>{s.manager_name}</td>
                  <td className="text-xs">{s.phone}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
