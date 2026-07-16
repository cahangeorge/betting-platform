import {
	Activity,
	BarChart3,
	Database,
	Globe2,
	Home,
	Settings,
	ShieldCheck,
	Ticket,
	Workflow
} from 'lucide-svelte';

export const workspaceNavigation = [
	{ href: '/', label: 'Acasă', description: 'Deciziile și stările de azi', icon: Home },
	{ href: '/prepare', label: 'Pregătire', description: 'Colectează și verifică datele', icon: Database },
	{ href: '/analyze', label: 'Analiză', description: 'Rulează modelele și compară selecțiile', icon: BarChart3 },
	{ href: '/opportunities?view=value', label: 'Oportunități', description: 'Selecții value și live', icon: Activity },
	{ href: '/tickets', label: 'Bilete', description: 'Revizuiește și urmărește biletele', icon: Ticket },
	{ href: '/monitoring', label: 'Monitorizare', description: 'Automatizări și istoricul joburilor', icon: Workflow }
] as const;

export const utilityNavigation = [
	{ href: '/prepare/data', label: 'Explorer de date', icon: Database }
] as const;

export const configurationNavigation = [
	{ href: '/settings/strategies', label: 'Strategii', icon: Settings },
	{ href: '/settings/countries-leagues', label: 'Listare țări/ligi', icon: Globe2 },
	{ href: '/settings/model-governance', label: 'Guvernanță modele', icon: ShieldCheck }
] as const;

export function isNavigationActive(pathname: string, href: string): boolean {
	const target = href.split('?')[0];
	return target === '/' ? pathname === '/' : pathname.startsWith(target);
}
