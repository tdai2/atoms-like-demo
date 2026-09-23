import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import BlogRoutes from './blog-routes';
import Index from './pages/Index';
import AuthCallback from './pages/AuthCallback';
import AuthError from './pages/AuthError';
import Placeholder from './pages/Placeholder';
// MODULE_IMPORTS_START
// MODULE_IMPORTS_END

const queryClient = new QueryClient();

const AppRoutes = () => (
  <Routes>
    <Route path="/" element={<Index />} />
    {/* <Route path="/blog/*" element={<BlogRoutes />} /> */}
    <Route path="/auth/callback" element={<AuthCallback />} />
    <Route path="/auth/error" element={<AuthError />} />
    <Route path="/templates/:id" element={<Placeholder useTemplateParam title="模板详情" desc="模板详情页" />} />
    <Route path="/docs" element={<Placeholder title="文档中心" desc="API 参考、快速上手与最佳实践将在这里呈现。" />} />
    <Route path="/changelog" element={<Placeholder title="更新日志" desc="记录每次模型升级与平台功能迭代。" />} />
    <Route path="/signin" element={<Placeholder title="登录 Atoms" desc="账号体系与团队协作能力即将开放。" />} />
    <Route path="/billing" element={<Placeholder title="订阅与计费" desc="在线支付与额度管理将在后续版本接入。" />} />
    {/* MODULE_ROUTES_START */}
    {/* MODULE_ROUTES_END */}
  </Routes>
);

const App = () => (
  <QueryClientProvider client={queryClient}>
    {/* MODULE_PROVIDERS_START */}
    {/* MODULE_PROVIDERS_END */}
    <TooltipProvider>
      <Toaster />
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </TooltipProvider>
    {/* MODULE_PROVIDERS_CLOSE */}
  </QueryClientProvider>
);

export default App;
export { AppRoutes };
