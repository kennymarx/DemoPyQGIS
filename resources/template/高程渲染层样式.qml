<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis maxScale="0" styleCategories="AllStyleCategories" minScale="1e+08" version="3.22.5-Białowieża" hasScaleBasedVisibilityFlag="0">
  <flags>
    <Identifiable>1</Identifiable>
    <Removable>1</Removable>
    <Searchable>1</Searchable>
    <Private>0</Private>
  </flags>
  <temporal fetchMode="0" mode="0" enabled="0">
    <fixedRange>
      <start></start>
      <end></end>
    </fixedRange>
  </temporal>
  <customproperties>
    <Option type="Map">
      <Option name="WMSBackgroundLayer" type="bool" value="false"/>
      <Option name="WMSPublishDataSourceUrl" type="bool" value="false"/>
      <Option name="embeddedWidgets/count" type="int" value="0"/>
      <Option name="identify/format" type="QString" value="Value"/>
    </Option>
  </customproperties>
  <pipe-data-defined-properties>
    <Option type="Map">
      <Option name="name" type="QString" value=""/>
      <Option name="properties"/>
      <Option name="type" type="QString" value="collection"/>
    </Option>
  </pipe-data-defined-properties>
  <pipe>
    <provider>
      <resampling maxOversampling="2" zoomedOutResamplingMethod="cubic" zoomedInResamplingMethod="cubic" enabled="false"/>
    </provider>
    <rasterrenderer opacity="1" classificationMin="-5" nodataColor="" type="singlebandpseudocolor" band="1" classificationMax="238" alphaBand="-1">
      <rasterTransparency/>
      <minMaxOrigin>
        <limits>MinMax</limits>
        <extent>WholeRaster</extent>
        <statAccuracy>Estimated</statAccuracy>
        <cumulativeCutLower>0.02</cumulativeCutLower>
        <cumulativeCutUpper>0.98</cumulativeCutUpper>
        <stdDevFactor>2</stdDevFactor>
      </minMaxOrigin>
      <rastershader>
        <colorrampshader maximumValue="238" minimumValue="-5" clip="0" classificationMode="1" labelPrecision="0" colorRampType="INTERPOLATED">
          <colorramp name="[source]" type="gradient">
            <Option type="Map">
              <Option name="color1" type="QString" value="247,252,255,255"/>
              <Option name="color2" type="QString" value="220,133,61,255"/>
              <Option name="discrete" type="QString" value="0"/>
              <Option name="rampType" type="QString" value="gradient"/>
              <Option name="stops" type="QString" value="0.186298;186,221,188,255:0.393029;254,240,201,255"/>
            </Option>
            <prop k="color1" v="247,252,255,255"/>
            <prop k="color2" v="220,133,61,255"/>
            <prop k="discrete" v="0"/>
            <prop k="rampType" v="gradient"/>
            <prop k="stops" v="0.186298;186,221,188,255:0.393029;254,240,201,255"/>
          </colorramp>
          <item label="-5" alpha="255" color="#f7fcff" value="-5"/>
          <item label="40" alpha="255" color="#baddbc" value="40.270413999999995"/>
          <item label="91" alpha="255" color="#fef0c9" value="90.50604700000001"/>
          <item label="238" alpha="255" color="#dc853d" value="238"/>
          <rampLegendSettings maximumLabel="" useContinuousLegend="1" suffix="" prefix="" direction="0" minimumLabel="" orientation="2">
            <numericFormat id="basic">
              <Option type="Map">
                <Option name="decimal_separator" type="QChar" value=""/>
                <Option name="decimals" type="int" value="6"/>
                <Option name="rounding_type" type="int" value="0"/>
                <Option name="show_plus" type="bool" value="false"/>
                <Option name="show_thousand_separator" type="bool" value="true"/>
                <Option name="show_trailing_zeros" type="bool" value="false"/>
                <Option name="thousand_separator" type="QChar" value=""/>
              </Option>
            </numericFormat>
          </rampLegendSettings>
        </colorrampshader>
      </rastershader>
    </rasterrenderer>
    <brightnesscontrast gamma="1" brightness="-19" contrast="0"/>
    <huesaturation grayscaleMode="0" colorizeBlue="128" colorizeRed="255" saturation="0" colorizeOn="0" colorizeStrength="100" invertColors="0" colorizeGreen="128"/>
    <rasterresampler maxOversampling="2" zoomedInResampler="cubic" zoomedOutResampler="cubic"/>
    <resamplingStage>resamplingFilter</resamplingStage>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
