import { Button, Result } from "antd";
import { useNavigate } from "react-router";

export default function NotFound() {
  const navigate = useNavigate();
  return (
    <div className="flex-1 flex items-center justify-center">
      <Result
        status="404"
        title="404"
        subTitle="页面不存在或已被移除"
        extra={
          <Button type="primary" onClick={() => navigate("/")}>
            返回首页
          </Button>
        }
      />
    </div>
  );
}
