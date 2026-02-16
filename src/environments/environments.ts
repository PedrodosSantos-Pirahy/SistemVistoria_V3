// Adicionamos esta definição de tipo para que o ficheiro se "auto-explique"
export const environment: {
  production: boolean;
  apiUrl: string;
  apiHistorico: string;
} = {
  production: false,
  apiUrl: 'http://192.168.53.193:5000',
  apiHistorico: 'http://192.168.53.193:5002'
};