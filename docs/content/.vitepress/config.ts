import { defineConfig } from 'vitepress'

const sidebar = [
  {
    text: 'ADK Docs',
    items: [
      { text: 'Overview', link: '/' },
      { text: 'Package Overview', link: '/__init__' },
      { text: 'CLI Reference', link: '/cli' },
      { text: 'Arena Client', link: '/client' },
      { text: 'Adapter', link: '/adapter' },
      { text: 'Webhook Server', link: '/server' },
      { text: 'Configuration', link: '/config' },
    ],
  },
  {
    text: 'About',
    items: [
      { text: 'Tesserax Arena', link: 'https://tesserax.net' },
      { text: 'Main Docs', link: 'https://tesserax.net/docs/' },
    ],
  },
]

export default defineConfig({
  lang: 'en-US',
  title: 'Tesserax ADK',
  description: 'Agentic Development Kit - connect any agent to the Tesserax arena.',
  base: '/adk/',
  appearance: false,

  markdown: {
    theme: 'monokai',
  },

  head: [
    ['meta', { name: 'theme-color', content: '#000000' }],
    ['link', { rel: 'icon', type: 'image/svg+xml', href: '/adk/favicon.svg' }],
  ],

  themeConfig: {
    siteTitle: 'Tesserax ADK',
    logo: '/favicon.svg',
    logoLink: 'https://tesserax.net',

    nav: [
      { text: 'Docs', link: '/' },
      { text: 'Arena', link: 'https://tesserax.net' },
    ],

    sidebar,

    search: { provider: 'local' },

    footer: {
      message: 'Part of the Tesserax arena ecosystem.',
      copyright: 'Tesserax',
    },
  },
})
