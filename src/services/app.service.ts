import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../environments/environments'; 
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  // Tipagem explícita para o TypeScript não se perder
  private http: HttpClient = inject(HttpClient);

  public readonly URL_PRINCIPAL = environment.apiUrl;      // Porta 5000
  public readonly URL_HISTORICO = environment.apiHistorico; // Porta 5002

  // ==========================================
  // API 5000 - VISTORIAS E AGENDAMENTOS
  // ==========================================

  // 🔑 Faltava este método!
  login(body: any): Observable<any> {
    return this.http.post<any>(`${this.URL_PRINCIPAL}/login`, body);
  }

  async getPendencias(timestamp: number, force = false): Promise<Response> {
    return fetch(`${this.URL_PRINCIPAL}/pendencias?t=${timestamp}${force ? '&force=true' : ''}`, {
        headers: { 'Cache-Control': 'no-cache' }
    });
  }

  getDadosCarga(placa: string): Observable<any> {
    return this.http.get<any>(`${this.URL_PRINCIPAL}/dados-carga/${placa}`);
  }

  consultarPlaca(placa: string): Observable<{ transportadora: string }> {
    return this.http.get<{ transportadora: string }>(`${this.URL_PRINCIPAL}/consultar-placa/${placa}`);
  }

  buscarTransportadoras(q: string): Observable<{codigo: string, nome: string}[]> {
    return this.http.get<{codigo: string, nome: string}[]>(`${this.URL_PRINCIPAL}/transportadoras?q=${encodeURIComponent(q)}`);
  }

  criarAgendamento(payload: any): Observable<any> {
    return this.http.post<any>(`${this.URL_PRINCIPAL}/criar-agendamento`, payload);
  }

  gerenciarAgendamento(payload: any): Observable<any> {
    return this.http.post<any>(`${this.URL_PRINCIPAL}/gerenciar-agendamento`, payload);
  }

  async enviarVistoria(formData: FormData): Promise<Response> {
    return fetch(`${this.URL_PRINCIPAL}/vistoria`, { method: 'POST', body: formData });
  }

  async cancelarVistoria(payload: any): Promise<Response> {
    return fetch(`${this.URL_PRINCIPAL}/cancelar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  }

  // ==========================================
  // API 5002 - MONITORAMENTO E HISTÓRICO
  // ==========================================

// No arquivo app.service.ts
// No arquivo app.service.ts
// 🔥 CORREÇÃO: Adicionamos o "derivado: string" no final dos parâmetros
getMonitoramento(page: number, limit: number, busca: string, local: string, status: string, erp: string, derivado: string, criador: string = ''): import('rxjs').Observable<any> {
    let params = new HttpParams()
      .set('page', page.toString())
      .set('limit', limit.toString());

    // 🔥 GARANTE QUE TODOS OS FILTROS SEJAM ENVIADOS PARA O PYTHON
    if (busca) params = params.set('q', busca);
    if (local && local !== 'Qualquer') params = params.set('local', local);
    if (status && status !== 'Todas') params = params.set('status', status);
    if (derivado && derivado !== 'Todas') params = params.set('derivado', derivado);
    if (criador) params = params.set('criador', criador);

    return this.http.get<any>(`${this.URL_HISTORICO}/monitoramento`, { params });
  }

  // 📜 Faltava este método para a tela de Histórico!
getHistorico(page: number, limit: number, placa: string, transportadora: string, local: string = ''): Observable<any> {
    // Adicionado &local=${local} ao final da URL
    const url = `${this.URL_HISTORICO}/historico?page=${page}&limit=${limit}&placa=${placa}&transportadora=${transportadora}&local=${local}`;
    return this.http.get<any>(url);
}

getAgendamentosDia(data: string, local: string): Observable<any[]> {
  // Adicionado &local=${local} para filtrar a ocupação por unidade
  return this.http.get<any[]>(`${this.URL_HISTORICO}/agendamentos-dia?data=${data}&local=${local}`);
}

  getDetalhesFinalizados(id: string): Observable<any> {
    return this.http.get<any>(`${this.URL_HISTORICO}/detalhes/${id}`);
  }

  verificarDuplicidade(params: string): Observable<{ duplicado: boolean }> {
    return this.http.get<{ duplicado: boolean }>(`${this.URL_HISTORICO}/verificar-duplicidade?${params}`);
  }

// Atualizado com o parâmetro 'local'
getDashboardCarga(data: string = '', local: string = 'Qualquer', derivado: string = 'Todas') {
    let params = new HttpParams();
    
    // 1. Coloca a data na mochila (se existir)
    if (data) params = params.set('data', data);
    
    // 2. Coloca o local na mochila (se não for 'Qualquer')
    if (local && local !== 'Qualquer') params = params.set('local', local);
    
    // 3. 🔥 NOVO: Coloca o filtro de fardos/derivados na mochila
    if (derivado && derivado !== 'Todas') params = params.set('derivado', derivado);
    
    // O Angular vai montar a URL assim: /dashboard-carga?data=2026-03-18&local=Matriz&derivado=Nao
    return this.http.get<any>(`${this.URL_HISTORICO}/dashboard-carga`, { params });
  }

  iniciarExportacao(params: {
    inicio: string; fim: string; status: string;
    local: string; derivado: string; transportadora: string; formato: string;
  }): Observable<{ job_id: string }> {
    const p = new HttpParams()
      .set('inicio', params.inicio)
      .set('fim', params.fim)
      .set('status', params.status)
      .set('local', params.local)
      .set('derivado', params.derivado)
      .set('transportadora', params.transportadora)
      .set('formato', params.formato);
    return this.http.get<{ job_id: string }>(`${this.URL_PRINCIPAL}/exportar-relatorio`, { params: p });
  }

  statusRelatorio(jobId: string): Observable<{ status: string; erro?: string }> {
    return this.http.get<{ status: string; erro?: string }>(`${this.URL_PRINCIPAL}/status-relatorio/${jobId}`);
  }

  downloadRelatorioUrl(jobId: string): string {
    return `${this.URL_PRINCIPAL}/download-relatorio/${jobId}`;
  }

  // Helpers para links (HTML)
  getPdfUrl(id: string): string { return `${this.URL_HISTORICO}/pdf/${id}`; }
  getFotoUrl(id: string, tipo: string): string { return `${this.URL_HISTORICO}/foto/${id}/${tipo}`; }
}