import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useAppStore } from '@/store/appStore';
import { useEffect } from 'react';

export function useSystemStatus() {
  const setSystemStatus = useAppStore(s => s.setSystemStatus);
  const setApiConnection = useAppStore(s => s.setApiConnection);

  const query = useQuery({
    queryKey: ['system-status'],
    queryFn: api.getStatus,
    refetchInterval: 5000,
    retry: 2,
  });

  useEffect(() => {
    if (query.data) {
      setSystemStatus(query.data);
      setApiConnection(query.data.contract_anchor_enabled ? 'connected' : 'degraded');
    } else if (query.isError) {
      setApiConnection('disconnected');
    }
  }, [query.data, query.isError, setSystemStatus, setApiConnection]);

  return query;
}
