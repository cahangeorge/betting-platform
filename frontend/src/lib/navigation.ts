import {
	Activity,
	BarChart3,
	Database,
	Home,
	Radio,
	Settings,
	Ticket,
	Workflow
} from 'lucide-svelte';

export const workspaceNavigation = [
	{ href: '/', label: 'Home', description: 'Today\'s decisions', icon: Home },
	{ href: '/prepare', label: 'Prepare', description: 'Collect and review data', icon: Database },
	{ href: '/analyze', label: 'Analyze', description: 'Run models and compare selections', icon: BarChart3 },
	{ href: '/opportunities?view=value', label: 'Opportunities', description: 'Value and live selections', icon: Activity },
	{ href: '/tickets', label: 'Tickets', description: 'Review and track tickets', icon: Ticket },
	{ href: '/monitoring', label: 'Monitoring', description: 'Automation and job history', icon: Workflow }
] as const;

export const utilityNavigation = [
	{ href: '/prepare/data', label: 'Data explorer', icon: Database },
	{ href: '/settings/strategies', label: 'Strategies', icon: Settings },
	{ href: '/opportunities?view=live', label: 'Live monitor', icon: Radio }
] as const;

export function isNavigationActive(pathname: string, href: string): boolean {
	const target = href.split('?')[0];
	return target === '/' ? pathname === '/' : pathname.startsWith(target);
}
