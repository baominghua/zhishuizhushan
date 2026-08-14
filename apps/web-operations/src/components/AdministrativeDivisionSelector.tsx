import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { AdministrativeDivisionItem } from "../api/types";

type DivisionValue = {
  countyCode?: string | null;
  countyName?: string | null;
  townCode?: string | null;
  townName?: string | null;
  villageCode?: string | null;
  villageName?: string | null;
};

type Level = AdministrativeDivisionItem["level"];

function provinceCodeFrom(countyCode: string) {
  return countyCode.length >= 2 ? `${countyCode.slice(0, 2)}0000` : "";
}

function cityCodeFrom(countyCode: string) {
  return countyCode.length >= 4 ? `${countyCode.slice(0, 4)}00` : "";
}

function useDivisions(level: Level, parentCode?: string, enabled = true) {
  return useQuery({
    queryKey: ["administrative-divisions", level, parentCode ?? ""],
    queryFn: () => api.administrativeDivisions(level, parentCode),
    enabled,
    staleTime: 10 * 60 * 1000,
  });
}

function selectedName(items: AdministrativeDivisionItem[], code: string, fallback = "") {
  return items.find((item) => item.code === code)?.name || fallback;
}

export function AdministrativeDivisionSelector({ value }: { value: DivisionValue }) {
  const initialCounty = value.countyCode || "";
  const [provinceCode, setProvinceCode] = useState(() => provinceCodeFrom(initialCounty));
  const [cityCode, setCityCode] = useState(() => cityCodeFrom(initialCounty));
  const [countyCode, setCountyCode] = useState(initialCounty);
  const [townCode, setTownCode] = useState(value.townCode || "");
  const [villageCode, setVillageCode] = useState(value.villageCode || "");

  const provinces = useDivisions("province");
  const cities = useDivisions("city", provinceCode, Boolean(provinceCode));
  const counties = useDivisions("county", cityCode, Boolean(cityCode));
  const towns = useDivisions("town", countyCode, Boolean(countyCode));
  const villages = useDivisions("village", townCode, Boolean(townCode));

  const provinceItems = provinces.data?.items ?? [];
  const cityItems = cities.data?.items ?? [];
  const countyItems = counties.data?.items ?? [];
  const townItems = towns.data?.items ?? [];
  const villageItems = villages.data?.items ?? [];
  const selectedPath = useMemo(() => [
    selectedName(provinceItems, provinceCode),
    selectedName(cityItems, cityCode),
    selectedName(countyItems, countyCode, value.countyName || ""),
    selectedName(townItems, townCode, value.townName || ""),
    selectedName(villageItems, villageCode, value.villageName || ""),
  ].filter(Boolean).join(" / "), [
    provinceItems, provinceCode, cityItems, cityCode, countyItems, countyCode,
    townItems, townCode, villageItems, villageCode, value,
  ]);

  const loading = provinces.isLoading || cities.isLoading || counties.isLoading || towns.isLoading || villages.isLoading;
  const error = provinces.error || cities.error || counties.error || towns.error || villages.error;

  return (
    <div className="division-selector field-span">
      <div className="division-grid">
        <DivisionSelect label="省级" value={provinceCode} items={provinceItems} loading={provinces.isLoading} onChange={(code) => {
          setProvinceCode(code); setCityCode(""); setCountyCode(""); setTownCode(""); setVillageCode("");
        }} />
        <DivisionSelect label="市级" value={cityCode} items={cityItems} loading={cities.isLoading} disabled={!provinceCode} onChange={(code) => {
          setCityCode(code); setCountyCode(""); setTownCode(""); setVillageCode("");
        }} />
        <DivisionSelect label="区县" value={countyCode} items={countyItems} loading={counties.isLoading} disabled={!cityCode} onChange={(code) => {
          setCountyCode(code); setTownCode(""); setVillageCode("");
        }} />
        <DivisionSelect label="乡镇" value={townCode} items={townItems} loading={towns.isLoading} disabled={!countyCode} onChange={(code) => {
          setTownCode(code); setVillageCode("");
        }} />
        <DivisionSelect label="村级" value={villageCode} items={villageItems} loading={villages.isLoading} disabled={!townCode} onChange={setVillageCode} optional />
      </div>
      <input type="hidden" name="countyCode" value={countyCode} />
      <input type="hidden" name="countyName" value={selectedName(countyItems, countyCode, value.countyName || "")} />
      <input type="hidden" name="townCode" value={townCode} />
      <input type="hidden" name="townName" value={selectedName(townItems, townCode, value.townName || "")} />
      <input type="hidden" name="villageCode" value={villageCode} />
      <input type="hidden" name="villageName" value={selectedName(villageItems, villageCode, value.villageName || "")} />
      <div className="division-selector-status" role="status">
        <span>{selectedPath || "请从省级开始选择行政区划"}</span>
        <small>{error ? "区划数据读取失败，请刷新后重试" : loading ? "正在读取区划数据" : "全国行政区划数据，含台湾省、香港和澳门"}</small>
      </div>
    </div>
  );
}

function DivisionSelect({ label, value, items, loading, disabled = false, optional = false, onChange }: {
  label: string;
  value: string;
  items: AdministrativeDivisionItem[];
  loading: boolean;
  disabled?: boolean;
  optional?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      <span>{label}{optional && <small>可选</small>}</span>
      <select value={value} disabled={disabled || loading} onChange={(event) => onChange(event.target.value)}>
        <option value="">{loading ? "读取中..." : disabled ? "请先选择上一级" : `请选择${label}`}</option>
        {items.map((item) => <option key={`${item.level}-${item.code}`} value={item.code}>{item.name}（{item.code}）</option>)}
      </select>
    </label>
  );
}
