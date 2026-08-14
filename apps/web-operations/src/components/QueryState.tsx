import { AlertTriangle, LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

interface QueryStateProps {
  loading: boolean;
  error: Error | null;
  children: ReactNode;
}

export function QueryState({ loading, error, children }: QueryStateProps) {
  if (loading) {
    return (
      <div className="query-state" role="status">
        <LoaderCircle className="spin" aria-hidden="true" />
        <span>正在读取正式数据</span>
      </div>
    );
  }
  if (error) {
    return (
      <div className="query-state error" role="alert">
        <AlertTriangle aria-hidden="true" />
        <div>
          <strong>数据暂时无法读取</strong>
          <p>{error.message}</p>
        </div>
      </div>
    );
  }
  return children;
}
