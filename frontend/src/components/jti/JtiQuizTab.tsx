import { jtiQuizApi } from '../../services/api/jti';
import QuizManagementTab from '../quiz/QuizManagementTab';

interface JtiQuizTabProps {
       language: string;
}

export default function JtiQuizTab({ language }: JtiQuizTabProps) {
       return <QuizManagementTab language={language} api={jtiQuizApi} appContext="jti" />;
}
