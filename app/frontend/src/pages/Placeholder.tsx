import { Link, useParams } from 'react-router-dom';
import { Construction, ArrowLeft } from 'lucide-react';
import SiteHeader from '@/components/SiteHeader';
import { TEMPLATES } from '@/data/site';

interface Props {
  title: string;
  desc: string;
  useTemplateParam?: boolean;
}

export default function Placeholder({ title, desc, useTemplateParam }: Props) {
  const { id } = useParams();
  const tpl = useTemplateParam ? TEMPLATES.find((t) => t.id === id) : undefined;
  const heading = tpl ? `${tpl.name} 模板` : title;
  const body = tpl ? tpl.summary : desc;

  return (
    <div className="min-h-screen bg-[#0b0c0e]">
      <SiteHeader />
      <main className="relative overflow-hidden">
        <div className="atom-grid absolute inset-0 opacity-60" aria-hidden />
        <div className="atom-glow absolute inset-0" aria-hidden />
        <div className="relative mx-auto flex min-h-[70vh] max-w-[1200px] flex-col items-start justify-center px-4 py-20 sm:px-6">
          <div className="w-full max-w-[560px] rounded-[14px] border border-[#24272d] bg-[#17191d] p-8">
            <span className="flex h-11 w-11 items-center justify-center rounded-[10px] border border-[#24272d] bg-[rgba(200,247,81,0.12)] text-[#c8f751]">
              <Construction size={20} />
            </span>
            <h1 className="mt-5 text-[28px] font-bold leading-[1.2] text-[#f2f4f5]">{heading}</h1>
            <p className="mt-3 text-[15px] leading-[1.65] text-[#a0a6af]">{body}</p>
            <p className="font-mono-ui mt-4 rounded-[10px] border border-[#24272d] bg-[#0b0c0e] px-3 py-2.5 text-[12px] text-[#6b727c]">
              status: not_built_yet — 该模块尚未接入，可在下一轮迭代中实现。
            </p>
            <Link
              to="/"
              className="focus-ring mt-6 inline-flex h-11 items-center gap-2 rounded-[10px] bg-[#c8f751] px-5 text-[15px] font-semibold text-[#0b0c0e] transition-colors hover:bg-[#b4e23c]"
            >
              <ArrowLeft size={16} /> 返回首页
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
