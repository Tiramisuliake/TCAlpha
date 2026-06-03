import { Form, InputNumber } from "antd";
import type { StrategyClassInfo } from "@/types";

interface StrategyParamsFormProps {
  /** 选中策略类的 params_schema；undefined / 空时提示无参数 */
  schema: StrategyClassInfo["params_schema"] | undefined;
}

/**
 * 按策略类的 params_schema 动态渲染参数输入项。
 *
 * - 字段映射到 Form 的 ["params", name]，提交时聚合为 params 对象，
 *   直接匹配后端 StrategyCreate.params / BacktestSubmit.params
 * - preserve=false：切换策略类时卸载的旧参数字段值不残留，避免污染提交
 * - int 类型 step=1，float step=0.1；min/max 来自后端 Field 的 ge/le
 */
export function StrategyParamsForm({ schema }: StrategyParamsFormProps) {
  if (!schema || Object.keys(schema).length === 0) {
    return <div className="text-xs text-slate-400">该策略无可调参数</div>;
  }

  return (
    <>
      {Object.entries(schema).map(([name, def]) => {
        const isInt = def.type.includes("int");
        return (
          <Form.Item
            key={name}
            label={def.title}
            name={["params", name]}
            initialValue={def.default as number}
            preserve={false}
          >
            <InputNumber
              className="!w-full"
              min={def.minimum ?? undefined}
              max={def.maximum ?? undefined}
              step={isInt ? 1 : 0.1}
            />
          </Form.Item>
        );
      })}
    </>
  );
}
