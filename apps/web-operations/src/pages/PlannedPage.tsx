import { Construction } from "lucide-react";

export function PlannedPage({ title, description }: { title: string; description: string }) {
  return <div className="standard-page"><section className="page-heading"><div><h1>{title}</h1><p>{description}</p></div></section><section className="planned-state"><Construction aria-hidden="true" /><h2>领域模型与权限点已确定</h2><p>当前尚未创建正式业务表，因此这里不展示演示台账。完成数据库迁移后，将按状态机接入真实办理数据。</p></section></div>;
}
