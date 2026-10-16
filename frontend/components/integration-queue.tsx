"use client";

import type { LeaveRequest } from "@/lib/api";
import { Empty, ErrorBox, Icon } from "./ui";
import type { Resource } from "./use-resource";

export function IntegrationQueue({ requests, onOpen }: { requests: Resource<LeaveRequest[]>; onOpen: (id: number) => void }) {
  const items = requests.data?.filter(item => ["pending", "error"].includes(item.zup_sync_status) || ["pending", "error"].includes(item.cancellation_sync_status || ""));
  return <section className="panel integration-queue"><div className="panel-heading"><h2>Передача в 1С и возврат дней</h2><button className="text-button" onClick={requests.reload}><Icon name="refresh" size={16} />Обновить</button></div>{requests.error ? <ErrorBox message={requests.error} retry={requests.reload} /> : !items?.length ? <Empty icon="check" title="Нет ожидающих команд" text="Очередь передачи отпусков и возвратов обработана." /> : <div className="request-preview-list">{items.map(item => <button key={item.id} className="request-preview" onClick={() => onOpen(item.id)}><span className="request-preview-main"><strong>№{item.id} · {item.employee_name}</strong><span>{item.cancellation_sync_status ? "Возврат дней" : "Передача отпуска"} · {[item.zup_sync_status, item.cancellation_sync_status].includes("error") ? "Требует повтора" : "В очереди"}</span></span><Icon name="chevron" size={16} /></button>)}</div>}</section>;
}
