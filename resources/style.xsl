<?xml version="1.0" encoding="utf-8"?>
<xsl:stylesheet version="3.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:atom="http://www.w3.org/2005/Atom">
  <xsl:output method="html" version="1.0" encoding="UTF-8" indent="yes"/>
  <xsl:template match="/atom:feed">
    <html xmlns="http://www.w3.org/1999/xhtml">
      <head>
        <title><xsl:value-of select="atom:title"/></title>
      </head>
      <body>
        <header>
          <h1><xsl:value-of select="atom:title"/></h1>
          <p>
            Podcast feed for
            <a>
              <xsl:attribute name="href">
                <xsl:value-of select="atom:link[@rel='self']/@href"/>
              </xsl:attribute>
              <xsl:value-of select="atom:link[@rel='self']/@href"/>
            </a>
          </p>
          <p><xsl:value-of select="atom:subtitle"/></p>
          <a>
            <xsl:attribute name="href">
              <xsl:value-of select="atom:link[@rel='alternate']/@href"/>
            </xsl:attribute>
            Podcast homepage
          </a>
        </header>
        <xsl:for-each select="atom:entry">
          <xsl:sort select="atom:updated" order="descending"/>
          <article>
            <h2>
              <a>
                <xsl:attribute name="href">
                  <xsl:value-of select="atom:link/@href"/>
                </xsl:attribute>
                <xsl:value-of select="atom:title"/>
              </a>
            </h2>
            <ul>
              <li><xsl:value-of select="atom:updated" /></li>
            </ul>
          </article>
        </xsl:for-each>
      </body>
    </html>
  </xsl:template>
</xsl:stylesheet>
